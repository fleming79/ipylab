// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import {
  InputDialog,
  showDialog,
  showErrorMessage
} from '@jupyterlab/apputils';
import { FileDialog } from '@jupyterlab/filebrowser';
import { IMainMenu, MainMenu } from '@jupyterlab/mainmenu';
import { IpylabModel } from './ipylab';

export class DialogModel extends IpylabModel {
  async operation(op: string, payload: any): Promise<any> {
    function _get_result(result: any): any {
      if (result.value === null) {
        throw new Error('Cancelled');
      }
      return result.value;
    }
    let result;
    switch (op) {
      case 'showDialog':
        result = await showDialog(payload);
        return { value: result.button.accept, isChecked: result.isChecked };
      case 'getBoolean':
        return await InputDialog.getBoolean(payload).then(_get_result);
      case 'getItem':
        return await InputDialog.getItem(payload).then(_get_result);
      case 'getNumber':
        return await InputDialog.getNumber(payload).then(_get_result);
      case 'getText':
        return await InputDialog.getText(payload).then(_get_result);
      case 'getPassword':
        return await InputDialog.getPassword(payload).then(_get_result);
      case 'showErrorMessage':
        return await showErrorMessage(
          payload.title,
          payload.error,
          payload.buttons
        );
      case 'getOpenFiles':
        payload.manager = this.defaultBrowser.model.manager;
        return await FileDialog.getOpenFiles(payload).then(_get_result);
      case 'getExistingDirectory':
        payload.manager = this.defaultBrowser.model.manager;
        return await FileDialog.getExistingDirectory(payload).then(_get_result);
      case 'generateMenu':
        return this._generateMenu(payload.options);
      default:
        return await super.operation(op, payload);
    }
  }

  private _generateMenu(options: IMainMenu.IMenuOptions) {
    const menu = MainMenu.generateMenu(
      this.commands,
      options,
      this.translator.load('jupyterlab')
    );
    return menu;
  }

  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'DialogModel' };
  }
}