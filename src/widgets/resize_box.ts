// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { BoxModel, BoxView } from '@jupyter-widgets/controls';
import { MODULE_NAME, MODULE_VERSION } from '../version';

/**
 * The model for a Resizeable box.
 */
export class ResizeBoxModel extends BoxModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'ResizeBoxModel',
      _model_module: MODULE_NAME,
      _model_module_version: MODULE_VERSION,
      _view_name: 'ResizeBoxView',
      _view_module: MODULE_NAME,
      _view_module_version: MODULE_VERSION
    };
  }
  _resizing = false;
}

/**
 * The view for a Resizeable box.
 */
export class ResizeBoxView extends BoxView {
  initialize(parameters: any): void {
    super.initialize(parameters);
    this.luminoWidget.removeClass('widget-box');
    this.luminoWidget.removeClass('jupyter-widgets');
    this.luminoWidget.addClass('ipylab-ResizeBox');
    this.resize();
    this.sizeObserver = new ResizeObserver(() => {
      if (!this.model._resizing && !this._resizing) {
        const clientWidth = this.el.clientWidth;
        const clientHeight = this.el.clientHeight;
        const width = this.el.style.width;
        const height = this.el.style.height;
        try {
          this.model._resizing = true;
          this._resizing = true;
          if (clientWidth && clientHeight) {
            this.model.set('size', [clientWidth, clientHeight]);
          }
          if (width && height) {
            this.model.set('width_height', [width, height]);
          }
          if ((width && height) || (clientWidth && clientHeight)) {
            this.model.save_changes();
          }
        } finally {
          this._resizing = false;
          this.model._resizing = false;
        }
        if (!width && !height) {
          this.resize();
        }
      }
    });
    this.sizeObserver.observe(this.el);
    this.listenTo(this.model, 'change:width_height', this.resize);
  }

  resize() {
    if (this._resizing) {
      return;
    }
    const [width, height] = this.model.get('width_height') ?? [null, null];
    if (width && height) {
      this._resizing = true;
      this.el.style.width = width;
      this.el.style.height = height;
      this._resizing = false;
    }
  }

  remove(): any {
    this?.sizeObserver?.disconnect();
    this.stopListening(this.model, 'change:size', this.resize);
    super.remove();
  }

  sizeObserver: ResizeObserver;
  model: ResizeBoxModel;
  _resizing = false;
}
