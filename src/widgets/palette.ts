// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { IPaletteItem } from '@jupyterlab/apputils';
import { ObservableMap } from '@jupyterlab/observables';
import { IDisposable } from '@lumino/disposable';
import { IpylabModel, JSONValue } from './ipylab';

/**
 * The model for a command palette.
 */
export class CommandPaletteModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): any {
    return {
      ...super.defaults(),
      _model_name: CommandPaletteModel.model_name,
      _model_module: CommandPaletteModel.model_module,
      _model_module_version: CommandPaletteModel.model_module_version,
      items: []
    };
  }

  /**
   * Initialize a CommandPaletteModel instance.
   *
   * @param attributes The base attributes.
   * @param options The initialization options.
   */
  initialize(attributes: any, options: any): void {
    super.initialize(attributes, options);
    this._customItems = new ObservableMap<IDisposable>();
    this._customItems.changed.connect(this._sendItems, this);
  }

  async operation(op: string, payload: any): Promise<JSONValue> {
    switch (op) {
      case 'addItem': {
        return this._addItem(payload);
      }
      case 'removeItem': {
        return this._removeItem(payload);
      }
      default:
        throw new Error(
          `operation='${op}' has not been implemented in CommandPaletteModel!`
        );
    }
  }

  /**
   * Close model
   *
   * @param comm_closed - true if the comm is already being closed. If false, the comm will be closed.
   *
   * @returns - a promise that is fulfilled when all the associated views have been removed.
   */
  close(comm_closed = false): Promise<void> {
    // can only be closed once.
    if (this._customItems) {
      this._customItems.changed.disconnect(this._sendItems, this);
      this._customItems.values().forEach(item => {
        if (!item.isDisposed) {
          item.dispose();
        }
      });
      this._customItems.clear();
      this._customItems = null;
    }
    return super.close(comm_closed);
  }

  /**
   * Send the list of items to the backend.
   */
  private _sendItems(sender?: object, args?: any): void {
    this.set('items', this._customItems.keys());
    this.save_changes();
  }

  /**
   * Add a new item to the command palette.
   *
   * @param options The item options.
   */
  private _addItem(options: IPaletteItem & { id: string }): JSONValue {
    const itemId = `${options.id} | ${options.category}`;
    if (this._customItems.has(itemId)) {
      this._removeItem(options);
    }
    const item = this.addItem(options);
    this._customItems.set(itemId, item);
    return { id: itemId };
  }

  /**
   * Add an item for the interface
   * @param options
   * @returns
   */
  addItem(options: any) {
    options.command = options.id;
    return this.interface.addItem(options);
  }

  /**
   * Remove an item (custom only) from the command pallet.
   *
   * @param payload The command payload.
   * @param payload.id
   */
  private _removeItem(options: IPaletteItem & { id: string }): null {
    const { id, category } = options;
    const itemId = `${id} | ${category}`;
    if (this._customItems.has(itemId)) {
      const cmd = this._customItems.get(itemId);
      if (cmd) {
        cmd.dispose();
      }
    }
    this._customItems.delete(itemId);
    return null;
  }

  get interface(): any {
    if (!IpylabModel.palette) {
      throw new Error('The command pallet is not loaded!');
    }

    return IpylabModel.palette;
  }

  static model_name = 'CommandPaletteModel';

  private _customItems: ObservableMap<IDisposable>;
}

/**
 * The model for the Launcher.
 */
export class LauncherModel extends CommandPaletteModel {
  get interface() {
    if (!IpylabModel.launcher) {
      throw new Error('The launcher is not loaded!');
    }
    return IpylabModel.launcher;
  }

  /**
   * Add an item for the launcher (interface)
   * @param options
   * @returns
   */
  addItem(options: any) {
    options.command = options.id;
    return this.interface.add(options);
  }

  static model_name = 'LauncherModel';
}
