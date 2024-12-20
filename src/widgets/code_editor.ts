// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { StringView } from '@jupyter-widgets/controls';
import { createStandaloneCell, SourceChange } from '@jupyter/ydoc';
import { CodeEditor, CodeEditorWrapper } from '@jupyterlab/codeeditor';
import {
  Completer,
  CompleterModel,
  CompletionHandler,
  ICompletionContext,
  ICompletionProvider,
  ProviderReconciliator
} from '@jupyterlab/completer';
import { Text } from '@jupyterlab/coreutils';
import { KernelMessage } from '@jupyterlab/services';
import { CommandRegistry } from '@lumino/commands';
import { JSONObject, UUID } from '@lumino/coreutils';
import { IDisposable } from '@lumino/disposable';
import { Message } from '@lumino/messaging';
import { Widget } from '@lumino/widgets';
import { IpylabModel } from './ipylab';
import { Tooltip } from '@jupyterlab/tooltip';

class IpylabCodeEditorWrapper extends CodeEditorWrapper {
  constructor(options: CodeEditorWrapper.IOptions & { view: CodeEditorView }) {
    super(options);
    this._view = options.view;
  }

  processMessage(msg: Message): void {
    super.processMessage(msg);
    this._view?.processLuminoMessage(msg);
  }

  /**
   * Dispose of the resources held by the widget.
   */
  dispose(): void {
    // Do nothing if already disposed.
    if (this.isDisposed) {
      return;
    }
    super.dispose();
    this._view?.remove();
    this._view = null!;
  }

  private _view: CodeEditorView;
}

class IpylabCompleter extends Completer {
  handleEvent(event: Event): void {
    super.handleEvent(event);
    if (
      !this.isHidden &&
      event.type === 'keydown' &&
      (event as KeyboardEvent).key === 'Enter'
    ) {
      // Select the value absorbing the keystroke.
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      this.selectActive();
    }
  }
}

/**
 * The model for a code editor.
 */
export class CodeEditorModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'CodeEditorModel',
      _view_name: 'CodeEditorView'
    };
  }

  initialize(attributes: any, options: any): void {
    super.initialize(attributes, options);
    this.on('change:mime_type', this.updateMimeType);
    this.editorModel = new CodeEditor.Model({
      mimeType: this.get('mime_type'),
      sharedModel: createStandaloneCell({ cell_type: 'code', source: '' })
    });
    this.editorModel.sharedModel.changed.connect(
      this.onSharedModelSourceChange,
      this
    );
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'clearUndoHistory':
        return this.editorModel.sharedModel.clearUndoHistory();
      case 'setValue':
        this._syncRequired = true;
        // Clear first for better reliability with plugins.
        this.editorModel.sharedModel.setSource('');
        this.editorModel.sharedModel.setSource(payload.value);
        this._syncRequired = false;
        return true;
      default:
        return await super.operation(op, payload);
    }
  }

  onSharedModelSourceChange() {
    if (!this._syncRequired) {
      this._syncRequired = true;
      setTimeout(async () => {
        if (this._syncRequired) {
          try {
            const value = this.editorModel.sharedModel.getSource();
            const payload = { sync: this.get('_sync'), value };
            await this.scheduleOperation('setValue', payload, 'auto');
          } finally {
            this._syncRequired = false;
          }
        }
      }, this.get('update_throttle_ms'));
    }
  }

  updateMimeType() {
    this.editorModel.mimeType = this.get('mime_type');
  }

  close(comm_closed?: boolean): Promise<void> {
    this.editorModel?.dispose();
    delete this.editorModel;
    return super.close(comm_closed);
  }
  editorModel: CodeEditor.IModel;
  _syncRequired = false;
}

export class CodeEditorView extends StringView {
  render() {
    super.render();
    this.luminoWidget.id = `ipylab-CodeEditor-${UUID.uuid4()}`;
    this.className = this.luminoWidget.id;
    this.editorWidget = new IpylabCodeEditorWrapper({
      view: this,
      factory: IpylabModel.editorServices.factoryService.newInlineEditor,
      model: this.model.editorModel
    });
    this.editorWidget.id = this.editorWidget.id || UUID.uuid4();
    this.editorWidget.addClass(this.className);
    this.model.on('change:mimeType', this.updateCompleter, this);
    this.model.on('change:completer_invoke_keys', this.updateCompleter, this);
    this.model.on('change:editor_options', this.updateEditorOptions, this);
    this.updateCompleter();
    this.updateEditorOptions();
    this.editorWidget.addClass('ipylab-CodeEditor');
    this.el.appendChild(this.editorWidget.node);

    // Initialize the command registry with the bindings.
    const useCapture = true;

    // Setup the keydown listener for the editor.
    this.editorWidget.node.addEventListener(
      'keydown',
      event => {
        Private.commands.processKeydownEvent(event);
      },
      useCapture
    );
  }

  remove() {
    this.model.off('change:mimeType', this.updateCompleter, this);
    this.model.off('change:completer_invoke_keys', this.updateCompleter, this);
    this.model.off('change:editor_options', this.updateEditorOptions, this);
    this.disposeCompleter();
    this.disposeCommands();
    super.remove();
  }
  private updateCompleter() {
    if (!this.model.editorModel.mimeType.toLowerCase().includes('python')) {
      this.disposeCompleter();
      this._loadCommands();
      return;
    }
    this._updateCompleter();
  }

  /**
   * Handle message sent to the front end.
   *
   * Used to focus or blur the widget.
   */

  handle_message(content: any): void {
    if (content.do === 'focus') {
      this.editorWidget.editor.focus();
    } else if (content.do === 'blur') {
      this.editorWidget.editor.blur();
    }
  }

  /**
   * Provide a completer for the widget.
   */
  _updateCompleter() {
    // Set up a completer.

    if (!this.handler) {
      const editor = this.editorWidget.editor;
      const model = new CompleterModel();
      // const completer = new Completer({ editor, model });
      const completer = new IpylabCompleter({ editor, model, showDoc: true });
      const timeout = 1000;
      const provider = new IpylabCompleterProvider(this);
      const reconciliator = new ProviderReconciliator({
        context: {
          widget: this.editorWidget,
          editor
        },
        providers: [provider],
        timeout: timeout
      });
      this.handler = new CompletionHandler({ completer, reconciliator });
      this.handler.editor = editor;

      completer.addClass('jp-ThemedContainer');
      completer.addClass(this.className);
      Widget.attach(completer, document.body);

      this._disposeCompleter = () => {
        model.dispose();
        completer.dispose();
        this.handler?.dispose();
        delete this.handler;
      };
    }
    this._loadCommands();
  }

  disposeCompleter() {
    if (this._disposeCompleter) {
      this._disposeCompleter();
      delete this._disposeCompleter;
    }
  }

  disposeCommands() {
    this.disposables.forEach(obj => obj.dispose());
    this.disposables.clear();
    this.tooltip?.dispose();
  }

  _loadCommands() {
    // Add the commands.
    this.disposeCommands();

    const cmdInvokeId = `${this.className}:invoke-completer`;
    const cmdTooltip = `${this.className}:tooltip-invoke`;
    const cmdEvaluate = `${this.className}:evaluate-code`;
    const cmdUndo = `${this.className}:undo`;
    const cmdRedo = `${this.className}:redo`;

    const selector = `.${this.className}`;
    const keyBindings: any = this.model.get('key_bindings');

    // Undo
    this.disposables.add(
      Private.commands.addCommand(cmdUndo, {
        execute: async () => {
          this.model.editorModel.sharedModel.undo();
        }
      })
    );
    this.disposables.add(
      Private.commands.addKeyBinding({
        selector,
        keys: keyBindings['undo'],
        command: cmdUndo
      })
    );

    // Redo
    this.disposables.add(
      Private.commands.addCommand(cmdRedo, {
        execute: async () => {
          this.model.editorModel.sharedModel.redo();
        }
      })
    );
    this.disposables.add(
      Private.commands.addKeyBinding({
        selector,
        keys: keyBindings['redo'],
        command: cmdRedo
      })
    );

    if (!this.model.editorModel.mimeType.toLowerCase().includes('python')) {
      return;
    }

    // Invoke completer
    this.disposables.add(
      Private.commands.addCommand(cmdInvokeId, {
        execute: () => {
          this.handler.invoke();
        }
      })
    );
    this.disposables.add(
      Private.commands.addKeyBinding({
        selector,
        keys: keyBindings['invoke_completer'],
        command: cmdInvokeId
      })
    );

    // Invoke tooltip (inspect)
    this.disposables.add(
      Private.commands.addCommand(cmdTooltip, {
        execute: async () => {
          const editor = this.editorWidget.editor;
          const code = editor.model.sharedModel.getSource();
          const position = editor.getCursorPosition();
          const cursor_pos = Text.jsIndexToCharIndex(
            editor.getOffsetAt(position),
            code
          );
          const payload = { code, cursor_pos };
          const msg = await this.model.scheduleOperation(
            'requestInspect',
            payload,
            'auto'
          );
          this.tooltip?.dispose();
          if (msg) {
            this.tooltip = new Tooltip({
              anchor: this.editorWidget,
              bundle: msg.data,
              editor: this.editorWidget.editor,
              rendermime: IpylabModel.rendermime as any
            });
            this.tooltip.addClass(this.className);
            Widget.attach(this.tooltip, document.body);
          }
        }
      })
    );
    this.disposables.add(
      Private.commands.addKeyBinding({
        selector,
        keys: keyBindings['invoke_tooltip'],
        command: cmdTooltip
      })
    );

    // Evaluate
    this.disposables.add(
      Private.commands.addCommand(cmdEvaluate, {
        execute: async () => {
          const editor = this.editorWidget.editor;
          const selection = editor.getSelection();
          const start = editor.getOffsetAt(selection.start);
          const end = editor.getOffsetAt(selection.end);
          const code = editor.model.sharedModel
            .getSource()
            .substring(start, end);
          await this.model.scheduleOperation('evaluateCode', { code }, 'auto');
        }
      })
    );
    this.disposables.add(
      Private.commands.addKeyBinding({
        selector,
        keys: keyBindings['evaluate'],
        command: cmdEvaluate
      })
    );
  }

  updateEditorOptions() {
    const options = this.model.get('editor_options');
    this.editorWidget.editor.setOptions(options);
  }

  model: CodeEditorModel;
  editorWidget: IpylabCodeEditorWrapper;
  _completerEnabled = false;
  className: string;
  handler?: CompletionHandler;
  tooltip?: Tooltip;

  _disposeCompleter?: () => void;
  disposables = new Set<IDisposable>();
}

export const KERNEL_PROVIDER_ID = 'CompletionProvider:ipylab:kernel';

/**
 * A kernel connector for completion handlers borrowed from Jupyterlab.
 */
export class IpylabCompleterProvider implements ICompletionProvider {
  readonly identifier = KERNEL_PROVIDER_ID;

  readonly rank: number = 550;

  readonly renderer: any = null;

  constructor(view: CodeEditorView) {
    this._view = view;
  }
  /**
   * The kernel completion provider is applicable only if the kernel is available.
   * @param context - additional information about context of completion request
   */
  async isApplicable(context: ICompletionContext): Promise<boolean> {
    return true;
  }
  /**
   * Fetch completion requests.
   *
   * @param request - The completion request text and details.
   */
  async fetch(
    request: CompletionHandler.IRequest,
    context: ICompletionContext
  ): Promise<CompletionHandler.ICompletionItemsReply> {
    const contents: KernelMessage.ICompleteRequestMsg['content'] = {
      code: request.text,
      cursor_pos: request.offset
    };
    const response: any = await this._view.model.scheduleOperation(
      'requestComplete',
      contents,
      'auto'
    );

    if (response.status !== 'ok') {
      throw new Error('Completion fetch failed to return successfully.');
    }

    const items = new Array<CompletionHandler.ICompletionItem>();
    const metadata = response.metadata._jupyter_types_experimental as
      | Array<JSONObject>
      | undefined;
    response.matches.forEach((label: any, index: any) => {
      if (metadata && metadata[index]) {
        items.push({
          label,
          type: metadata[index].type as string,
          insertText: metadata[index].text as string
        });
      } else {
        items.push({ label });
      }
    });
    return {
      start: response.cursor_start,
      end: response.cursor_end,
      items
    };
  }

  /**
   * Kernel provider will use the inspect request to lazy-load the content
   * for document panel.
   */
  async resolve(
    item: CompletionHandler.ICompletionItem,
    context: ICompletionContext,
    patch?: Completer.IPatch | null
  ): Promise<CompletionHandler.ICompletionItem> {
    const { editor, session } = context;
    if (session && editor) {
      let code = editor.model.sharedModel.getSource();

      const position = editor.getCursorPosition();
      let offset = Text.jsIndexToCharIndex(editor.getOffsetAt(position), code);
      if (patch) {
        const { start, value } = patch;
        code = code.substring(0, start) + value;
        offset = offset + value.length;
      }

      const contents: KernelMessage.IInspectRequestMsg['content'] = {
        code,
        cursor_pos: offset,
        detail_level: 0
      };

      const msg = await this._view.model.scheduleOperation(
        'requestInspect',
        contents,
        'auto'
      );

      const value = msg.content;
      if (value.status !== 'ok' || !value.found) {
        return item;
      }
      item.documentation = value.data['text/plain'] as string;
      return item;
    }
    return item;
  }

  /**
   * Kernel provider will activate the completer in continuous mode after
   * the `.` character.
   */
  shouldShowContinuousHint(visible: boolean, changed: SourceChange): boolean {
    const sourceChange = changed.sourceChange;
    // eslint-disable-next-line eqeqeq
    if (sourceChange == null) {
      return true;
    }

    // eslint-disable-next-line eqeqeq
    if (sourceChange.some(delta => delta.delete != null)) {
      return false;
    }

    return sourceChange.some(
      delta =>
        // eslint-disable-next-line eqeqeq
        delta.insert != null &&
        (delta.insert === '.' || (!visible && delta.insert.trim().length > 0))
    );
  }
  _view: CodeEditorView;
}

/**
 * A namespace for private data
 */
namespace Private {
  export const commands = new CommandRegistry();
}
