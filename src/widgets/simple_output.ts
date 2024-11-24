// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.
import { DOMWidgetView } from '@jupyter-widgets/base';
import * as nbformat from '@jupyterlab/nbformat';
import { IOutput } from '@jupyterlab/nbformat';
import {
  OutputArea,
  OutputAreaModel,
  SimplifiedOutputArea
} from '@jupyterlab/outputarea';
import { IOutputModel } from '@jupyterlab/rendermime';
import { Message } from '@lumino/messaging';
import $ from 'jquery';
import { IpylabModel } from './ipylab';

class IpylabOutputAreaModel extends OutputAreaModel {
  /**
   * Whether a new value should be consolidated with the previous output.
   *
   * This will only be called if the minimal criteria of both being stream
   * messages of the same type.
   */
  protected shouldCombine(options: {
    value: nbformat.IOutput;
    lastModel: IOutputModel;
  }): boolean {
    if (
      options.value.name === 'stdout' &&
      this._continuousCount < this.maxContinuous
    ) {
      this._continuousCount++;
      return true;
    } else {
      this._continuousCount = 0;
    }
    return false;
  }
  /**
   * Remove oldest outputs to the length limit.
   */
  removeOldest(maxLength: number) {
    if (this.list.length > maxLength) {
      this.list.removeRange(0, this.list.length - maxLength);
    }
  }

  private _continuousCount = 0;
  maxContinuous = 100;
}

/**
 * The model for a panel.
 */
export class SimpleOutputModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'SimpleOutputModel',
      _view_name: 'SimpleOutputView'
    };
  }

  setReady(): void {
    this.on('change:max_continuous_streams', this.configure, this);
    this.on('change:max_outputs', this.configure, this);
    this.configure();
    this.outputAreaModel.changed.connect(this._outputAreaModelChange, this);
    super.setReady();
  }

  protected async onCustomMessage(msg: any) {
    const content = typeof msg === 'string' ? JSON.parse(msg) : msg;
    if ('add' in content) {
      this.add(content.add);
    } else if ('clear' in content) {
      this.outputAreaModel.clear(content.clear);
    } else {
      await super.onCustomMessage(content);
    }
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'setOutputs':
        return await this.setOutputs(payload);
      default:
        return await super.operation(op, payload);
    }
  }

  configure() {
    this._maxOutputs = this.get('max_outputs');
    this.outputAreaModel.maxContinuous = this.get('max_continuous_streams');
  }

  _outputAreaModelChange() {
    const length = this.outputAreaModel.length;
    if (this.outputAreaModel.length > this._maxOutputs) {
      this.outputAreaModel.removeOldest(this._maxOutputs);
      return;
    }
    if (length !== this.get('length')) {
      this.set('length', length);
      this.save_changes();
    }
  }

  async setOutputs({ outputs }: { outputs: Array<IOutput> }) {
    this.outputAreaModel.clear(true);
    this.add(outputs);
    return this.outputAreaModel.length;
  }

  add(items: Array<IOutput>) {
    for (const output of items) {
      this.outputAreaModel.add(output);
    }
  }

  close(comm_closed?: boolean) {
    this.outputAreaModel.changed.disconnect(this._outputAreaModelChange, this);
    this.outputAreaModel.dispose();
    return super.close(comm_closed);
  }
  private _maxOutputs = 100;
  outputAreaModel = new IpylabOutputAreaModel({ trusted: true });
}

export class SimpleOutputView extends DOMWidgetView {
  _createElement(tagName: string): HTMLElement {
    this.luminoWidget = new IpylabSimplifiedOutputArea({
      view: this,
      rendermime: IpylabModel.rendermime,
      contentFactory: OutputArea.defaultContentFactory,
      model: this.model.outputAreaModel,
      promptOverlay: false
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
  model: SimpleOutputModel;
  luminoWidget: IpylabSimplifiedOutputArea;
}

class IpylabSimplifiedOutputArea extends SimplifiedOutputArea {
  constructor(
    options: IpylabSimplifiedOutputArea.IOptions & OutputArea.IOptions
  ) {
    const view = options.view;
    delete (options as any).view;
    super(options);
    this._view = view;
  }

  processMessage(msg: Message): void {
    super.processMessage(msg);
    this._view?.processLuminoMessage(msg);
  }

  /**
   * Dispose the widget.
   *
   * This causes the view to be destroyed as well with 'remove'
   */
  dispose(): void {
    if (this.isDisposed) {
      return;
    }
    super.dispose();
    this._view?.remove();
    this._view = null!;
  }

  private _view: SimpleOutputView;
}

export namespace IpylabSimplifiedOutputArea {
  export interface IOptions {
    view: SimpleOutputView;
  }
}
