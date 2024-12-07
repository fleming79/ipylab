// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { DOMWidgetModel, DOMWidgetView } from '@jupyter-widgets/base';
import { Message } from '@lumino/messaging';
import { PanelLayout, Widget } from '@lumino/widgets';
import $ from 'jquery';
import { MODULE_NAME, MODULE_VERSION } from '../version';
import { IpylabModel } from './ipylab';

/**
 *
 * Inspiration:  @jupyterlab/logconsole -> ScrollingWidget
 *
 * Implements a panel which autoscrolls the content.
 */
export class AutoScroll<T extends Widget> extends Widget {
  constructor({ content, ...options }: AutoScroll.IOptions<T>) {
    super(options);
    this._view = options.view;
    this.layout = new PanelLayout();
    this._sentinel = document.createElement('div');
    this._view.model.on('change:content', this.loadContent, this);
    this.loadContent();
  }

  /**
   * The content widget.
   */
  get content() {
    return this._content;
  }

  set content(content: Widget | undefined) {
    if (this._content === content) {
      return;
    }
    if (this._content) {
      this.layout.removeWidget(this._content);
    }
    this._content = content;
    if (content) {
      (this.layout as PanelLayout).addWidget(content);
    }
  }

  async loadContent() {
    const id = this._view.model.get('content');
    this.content = id ? await IpylabModel.toLuminoWidget({ id }) : undefined;
    this.update();
  }

  scrollOnce() {
    if (this.enabled) {
      this._sentinel.scrollIntoView({ behavior: 'instant' as ScrollBehavior });
    }
  }

  private _disconnectObserver() {
    if (this._observer) {
      this._observer.disconnect();
      delete this._observer;
    }
  }

  update(): void {
    this._disconnectObserver();
    if (this.node.contains(this._sentinel)) {
      this.node.removeChild(this._sentinel);
    }
    this.enabled = this._view.model.get('enabled');
    if (!this.enabled) {
      (this.node as any).onscrollend = null;
      return;
    }
    this._sentinel.textContent = this._view.model.get('sentinel_text') || '';

    if (this._view.model.get('mode') === 'start') {
      this.node.prepend(this._sentinel);
    } else {
      this.node.appendChild(this._sentinel);
    }
    (this.node as any).onscrollend = (event: Event) => {
      if (this.enabled) {
        this.scrollOnce();
      }
    };

    this._observer = new IntersectionObserver(
      args => {
        if (!args[0].isIntersecting) {
          this.scrollOnce();
        }
      },
      { root: this.node }
    );
    this._observer.observe(this._sentinel);
    this.scrollOnce();
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
    this._disconnectObserver();
    super.dispose();
    this._view?.model?.off('change:content', this.loadContent, this);
    this._view?.remove();
    this._view = null!;
  }
  enabled: boolean;
  private _content?: Widget;
  private _observer: IntersectionObserver | null = null;
  private _sentinel: HTMLDivElement;
  private _view: DOMWidgetView;
}

export namespace AutoScroll {
  export interface IOptions<T extends Widget> extends Widget.IOptions {
    content?: T;
    view: DOMWidgetView;
  }
}

/**
 * The model for a logger.
 */
export class AutoscrollModel extends DOMWidgetModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'AutoscrollModel',
      _model_module: MODULE_NAME,
      _model_module_version: MODULE_VERSION,
      _view_name: 'AutoscrollView',
      _view_module: MODULE_NAME,
      _view_module_version: MODULE_VERSION
    };
  }
}

/**
 * The view for a AutoScroll.
 */

export class AutoscrollView extends DOMWidgetView {
  _createElement(tagName: string): HTMLElement {
    this.luminoWidget = new AutoScroll({
      view: this
    });
    return this.luminoWidget.node;
  }

  _setElement(el: HTMLElement): void {
    this.el = this.luminoWidget.node;
    this.$el = $(this.luminoWidget.node);
  }

  update(options?: any): void {
    super.update();
    this.luminoWidget.update();
  }

  model: AutoscrollModel;
  luminoWidget: AutoScroll<Widget>;
}
