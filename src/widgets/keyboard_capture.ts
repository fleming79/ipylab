// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { DOMWidgetView, DOMWidgetModel } from '@jupyter-widgets/base';
import { MODULE_NAME, MODULE_VERSION } from '../version';

export class KeyboardCaptureModel extends DOMWidgetModel {
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      tabbable: false,
      _model_name: 'KeyboardCaptureModel',
      _model_module: MODULE_NAME,
      _model_module_version: MODULE_VERSION,
      _view_name: 'KeyboardCaptureView',
      _view_module: MODULE_NAME,
      _view_module_version: MODULE_VERSION
    };
  }
}

export class KeyboardCaptureView extends DOMWidgetView {
  /**
   * Called when view is rendered.
   */
  render(): void {
    super.render();
    this.el.classList.add('ipylab-KeyboardCapture');
    this.update();
  }

  /**
   * Dictionary of events and handlers
   */
  events(): { [e: string]: string } {
    return { keydown: '_handle_key_event' };
  }

  /**
   * Update the contents of this view
   *
   * Called when the model is changed. The model may have been
   * changed by another view or by a state update from the back-end.
   */
  update(): void {
    this.el.disabled = this.model.get('disabled');
    this.updateTabindex();

    const tooltip = this.model.get('tooltip');
    const description = this.model.get('description');
    const icon = this.model.get('icon');

    this.el.setAttribute('title', tooltip ?? description);

    if (description.length || icon.length) {
      this.el.textContent = '';
      if (icon.length) {
        const i = document.createElement('i');
        i.classList.add('fa');
        i.classList.add(
          ...icon
            .split(/[\s]+/)
            .filter(Boolean)
            .map((v: string) => `fa-${v}`)
        );
        if (description.length === 0) {
          i.classList.add('center');
        }
        this.el.appendChild(i);
      }
      this.el.appendChild(document.createTextNode(description));
    }
    return super.update();
  }

  /**
   * Handles a key event.
   */
  _handle_key_event(event: KeyboardEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.send({
      event: event.type,
      keyCode: event.key,
      repeat: event.repeat,
      shiftKey: event.shiftKey,
      ctrlKey: event.ctrlKey,
      altKey: event.altKey
    });
  }

  preinitialize() {
    // Must set this before the initialize method creates the element
    this.tagName = 'button';
  }

  el: HTMLButtonElement;
}
