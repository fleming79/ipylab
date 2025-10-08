// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { JupyterLuminoPanelWidget, unpack_models } from '@jupyter-widgets/base';
import { BoxModel, BoxView } from '@jupyter-widgets/controls';
import { MODULE_NAME, MODULE_VERSION } from '../version';
import { TitleModel } from '../widgets/title';

/**
 * The model for a panel.
 */
export class PanelModel extends BoxModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'PanelModel',
      _model_module: MODULE_NAME,
      _model_module_version: MODULE_VERSION,
      _view_name: 'PanelView',
      _view_module: MODULE_NAME,
      _view_module_version: MODULE_VERSION
    };
  }

  static serializers = {
    ...BoxModel.serializers,
    title: { deserialize: unpack_models }
  };
}

/**
 * The view for a Panel.
 */
export class PanelView extends BoxView {
  initialize(parameters: any): void {
    super.initialize(parameters);
    this.listenTo(this.model.get('title'), 'change', this.update_title);
    this.luminoWidget.removeClass('widget-box');
    this.luminoWidget.removeClass('jupyter-widgets');
    this.luminoWidget.addClass('ipylab-Panel');
    this.update_title();
  }

  update_title() {
    const title: TitleModel = this.model.get('title');
    title.update_title(this.luminoWidget.title);
  }

  model: PanelModel;
  luminoWidget: JupyterLuminoPanelWidget;
}
