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
}

/**
 * The view for a Resizeable box.
 */
export class ResizeBoxView extends BoxView {
  initialize(parameters: any): void {
    super.initialize(parameters);
    if (Object.keys(this.model.views).length === 1) {
      this.makeObserver();
    }
  }

  makeObserver() {
    if (this.sizeObserver) {
      return;
    }
    this.sizeObserver = new ResizeObserver(() => {
      this.model.set('width', this.el.clientWidth);
      this.model.set('height', this.el.clientHeight);
      this.model.save_changes();
    });
    this.sizeObserver.observe(this.el);
    this.luminoWidget.removeClass('widget-box');
    this.luminoWidget.removeClass('jupyter-widgets');
    this.luminoWidget.addClass('ipylab-ResizeBox');
  }


  remove(): any {
    this.sizeObserver.disconnect();
    super.remove();
    for (const k in this.model.views) {
      this.model.views[k].then(view => (view as ResizeBoxView).makeObserver());
      break;
    }
  }

  sizeObserver: ResizeObserver;
  model: ResizeBoxModel;
}
