// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { DOMWidgetView } from '@jupyter-widgets/base';
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
import $ from 'jquery';
import { IpylabModel } from './ipylab';

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
    this.on('change:value', this.onValueChange);
    this.on('change:mime_type', this.updateMimeType);
    this.editorModel = new CodeEditor.Model({
      mimeType: this.get('mime_type'),
      sharedModel: createStandaloneCell({
        cell_type: 'code',
        source: this.get('value')
      })
    });
    this.editorModel.sharedModel.changed.connect(
      this.onSharedModelSourceChange,
      this
    );
  }
  onSharedModelSourceChange() {
    const value = this.editorModel.sharedModel.getSource();
    if (this.get('value') !== value) {
      this.set('value', value);
      this.save_changes();
    }
  }

  onValueChange() {
    const value = this.get('value');
    if (value !== this.editorModel.sharedModel.source) {
      this.editorModel.sharedModel.setSource(value);
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
}

export class CodeEditorView extends DOMWidgetView {
  _createElement(tagName: string): HTMLElement {
    this.luminoWidget = new IpylabCodeEditorWrapper({
      view: this,
      factory: IpylabModel.editorServices.factoryService.newInlineEditor,
      model: this.model.editorModel
    });
    this.luminoWidget.id = this.luminoWidget.id || UUID.uuid4();
    this.model.on('change:mimeType', this.updateCompleter, this);
    this.model.on('change:completer_invoke_keys', this.updateCompleter, this);
    this.updateCompleter();
    return this.luminoWidget.node;
  }

  _setElement(el: HTMLElement): void {
    if (this.el || el !== this.luminoWidget.node) {
      throw new Error('Cannot reset the DOM element.');
    }

    this.el = this.luminoWidget.node;
    this.$el = $(this.luminoWidget.node);
  }

  remove() {
    this.model.off('change:mimeType', this.updateCompleter, this);
    this.model.off('change:completer_invoke_keys', this.updateCompleter, this);
    this.disposeCompleter();
    super.remove();
  }
  private updateCompleter() {
    if (!this.model.editorModel.mimeType.toLowerCase().includes('python')) {
      this.disposeCompleter();
      return;
    }
    this._updateCompleter();
  }

  /**
   * Provide a completer for the widget.
   */
  _updateCompleter() {
    // Set up a completer.

    if (!this.handler) {
      const widget = this.luminoWidget;
      this.className = `ipylab-CodeEditor-${widget.id}`;
      const editor = widget.editor;
      const model = new CompleterModel();
      // const completer = new Completer({ editor, model });
      const completer = new IpylabCompleter({ editor, model, showDoc: true });
      const timeout = 1000;
      const provider = new IpylabCompleterProvider(this);
      const reconciliator = new ProviderReconciliator({
        context: {
          widget: widget,
          editor
        },
        providers: [provider],
        timeout: timeout
      });
      this.handler = new CompletionHandler({ completer, reconciliator });
      this.handler.editor = editor;
      // Hide the widget when it first loads.
      // completer.hide();
      completer.addClass('jp-ThemedContainer');
      completer.addClass(this.className);
      Widget.attach(completer, document.body);
      widget.addClass(this.className);

      // Initialize the command registry with the bindings.
      const useCapture = true;

      // Setup the keydown listener for the document.
      widget.node.addEventListener(
        'keydown',
        event => {
          Private.commands.processKeydownEvent(event);
        },
        useCapture
      );

      this._disposeCompleter = () => {
        model.dispose();
        completer.dispose();
        this.handler?.dispose();
        delete this.handler;
        this.cmdInvoke?.dispose();
        this.kbInvoke?.dispose();
      };
    }
    this._updateCommands();
  }

  disposeCompleter() {
    if (this._disposeCompleter) {
      this._disposeCompleter();
      delete this._disposeCompleter;
    }
  }

  _updateCommands() {
    // Add the commands.
    this.cmdInvoke?.dispose();
    this.kbInvoke?.dispose();
    this.kbCompleterSelect?.dispose();
    this.kbEvaluate?.dispose();

    // Invoke completer
    const cmdInvokeId = `${this.className}:invoke-completer`;
    const cmdEvaluate = `${this.className}:evaluate-code`;

    const selector = `.${this.className}`;
    const keyBindings: any = this.model.get('key_bindings');

    this.cmdInvoke = Private.commands.addCommand(cmdInvokeId, {
      execute: () => {
        this.handler.invoke();
      }
    });

    this.kbInvoke = Private.commands.addKeyBinding({
      selector,
      keys: keyBindings['invoke_completer'],
      command: cmdInvokeId
    });

    // Evaluate selected code
    Private.commands.addCommand(cmdEvaluate, {
      execute: async () => {
        const editor = this.luminoWidget.editor;
        const selection = editor.getSelection();
        const start = editor.getOffsetAt(selection.start);
        const end = editor.getOffsetAt(selection.end);
        const code = editor.model.sharedModel.getSource().substring(start, end);
        await this.model.scheduleOperation(
          'evaluateCode',
          { evaluate: code },
          'auto'
        );
      }
    });
    this.kbEvaluate = Private.commands.addKeyBinding({
      selector,
      keys: keyBindings['evaluate'],
      command: cmdEvaluate
    });
  }

  model: CodeEditorModel;
  luminoWidget: IpylabCodeEditorWrapper;
  _completerEnabled = false;
  className: string;
  handler?: CompletionHandler;
  cmdInvoke?: IDisposable;
  kbInvoke?: IDisposable;
  kbCompleterSelect?: IDisposable;
  kbEvaluate?: IDisposable;
  _disposeCompleter?: () => void;
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
      const kernel = this._view.model.kernel;
      if (!code || !kernel) {
        return item;
      }
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
      const msg = await kernel.requestInspect(contents);
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
