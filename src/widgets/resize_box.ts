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
  primaryView: ResizeBoxView | null;
}

/**
 * The view for a Resizeable box.
 */
export class ResizeBoxView extends BoxView {
  initialize(parameters: any): void {
    super.initialize(parameters);
    if (!this.model.primaryView) {
      this.makeObserver();
    } else {
      this.listenTo(this.model, 'change:size', this.updateSize);
      requestAnimationFrame(() => this.updateSize());
    }
  }

  makeObserver() {
    if (this.sizeObserver) {
      return;
    }
    this.model.primaryView = this;
    this.sizeObserver = new ResizeObserver(() => {
      const size = [this.el.clientWidth, this.el.clientHeight];
      this.model.set('size', size);
      this.model.save_changes();
    });
    this.sizeObserver.observe(this.el);
    this.luminoWidget.removeClass('widget-box');
    this.luminoWidget.removeClass('jupyter-widgets');
    this.luminoWidget.addClass('ipylab-ResizeBox');
    this.stopListening(this.model, 'change:size', this.updateSize);
  }

  updateSize() {
    const view = this.model.primaryView;
    if (view && view !== this) {
      this.el.style.width = view.el.style.width;
      this.el.style.height = view.el.style.height;
    }
  }

  remove(): any {
    this?.sizeObserver?.disconnect();
    this.stopListening(this.model, 'change:size', this.updateSize);
    super.remove();
    if (this.model.primaryView === this) {
      for (const k in this.model.views) {
        this.model.views[k].then(view => {
          const view_ = view as ResizeBoxView;
          view_.makeObserver();
        });
        break;
      }
    }
  }

  sizeObserver: ResizeObserver;
  model: ResizeBoxModel;
}
