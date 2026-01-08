// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { DOMWidgetModel, DOMWidgetView } from '@jupyter-widgets/base';
import { LabIcon } from '@jupyterlab/ui-components';
import { MODULE_NAME, MODULE_VERSION } from '../version';

export class IconView extends DOMWidgetView {
  initialize(parameters: any) {
    super.initialize(parameters);
    this.iconElement = document.createElement('div');
    this.el.appendChild(this.iconElement);
    this.update();
  }

  update() {
    const { labIcon } = this.model;
    if (labIcon) {
      labIcon.render(this.iconElement, {
        props: { tag: 'div' }
      });
    }
  }

  model: IconModel;
  protected iconElement: HTMLElement;
}

/**
 * The model for an icon widget.
 */
export class IconModel extends DOMWidgetModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'IconModel',
      _model_module: MODULE_NAME,
      _model_module_version: MODULE_VERSION,
      _view_name: 'IconView',
      _view_module: MODULE_NAME,
      _view_module_version: MODULE_VERSION
    };
  }

  /**
   * Initialize a LabIcon instance.
   *
   * @param attributes The base attributes.
   * @param options The initialization options.
   */
  initialize(attributes: any, options: any): void {
    super.initialize(attributes, options);
    const name = this.get('name');
    const svgstr =
      this.get('svgstr') ||
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle class="jp-icon-selectable jp-icon3" cx="12" cy="12" r="12" fill="#616161" /></svg>';
    this._labIcon = new LabIcon({ name, svgstr });
    this.on('change:name change:svgstr', this.updateIcon);
    this.updateIcon();
  }

  get labIcon(): LabIcon {
    return this._labIcon;
  }

  /**
   * Update the LabIcon when model changes occur
   */
  updateIcon() {
    const svgstr: string = this.get('svgstr');
    if (svgstr) {
      this._labIcon.svgstr = svgstr;
      this.trigger('change');
    }
  }

  protected _labIcon: LabIcon;
}
