// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { DOMWidgetModel, DOMWidgetView } from '@jupyter-widgets/base';
import { createStandaloneCell } from '@jupyter/ydoc';
import { CodeEditor, CodeEditorWrapper } from '@jupyterlab/codeeditor';
import { Message } from '@lumino/messaging';
import $ from 'jquery';
import { MODULE_NAME, MODULE_VERSION } from '../version';
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

/**
 * The model for a code editor.
 */
export class CodeEditorModel extends DOMWidgetModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'CodeEditorModel',
      _model_module: MODULE_NAME,
      _model_module_version: MODULE_VERSION,
      _view_name: 'CodeEditorView',
      _view_module: MODULE_NAME,
      _view_module_version: MODULE_VERSION
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
    return this.luminoWidget.node;
  }

  _setElement(el: HTMLElement): void {
    if (this.el || el !== this.luminoWidget.node) {
      throw new Error('Cannot reset the DOM element.');
    }

    this.el = this.luminoWidget.node;
    this.$el = $(this.luminoWidget.node);
  }

  model: CodeEditorModel;
  luminoWidget: IpylabCodeEditorWrapper;
}
