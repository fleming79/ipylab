// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { PromiseDelegate, UUID } from '@lumino/coreutils';
import { Signal } from '@lumino/signaling';
import { IpylabModel } from './ipylab';
import { IObservableDisposable } from '@lumino/disposable';
import { Widget } from '@lumino/widgets';
import { ILabShell } from '@jupyterlab/application';
/**
 * Provides a connection to an object using a unique 'cid'.
 *
 *
 * An object must be registered static method `ConnectionModel.registerConnection`
 * to establish the connection. The base class expects the object to be
 * register before it is created. Subclasses can indicate
 * by using a 'pending' promise. The
 * The 'cid' can generated in Python first, or generated in the Frontend if a 'cid'
 * isn't provided.
 *
 * The object is set to `this.base`.
 */
export class ConnectionModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ConnectionModel' };
  }

  async ipylabInit(base: any = null) {
    this.cid_ = this.get('cid');
    try {
      base = await this.getObject();
      base.disposed.connect(this._base_disposed, this);
      await super.ipylabInit(base);
    } catch (e) {
      this.close();
      this.error(`Failed to establish connection for cid=${this.cid_} ${e}`);
    }
  }

  _base_disposed() {
    this.set('auto_dispose', false);
    this.close(false);
  }

  close(comm_closed = false): Promise<void> {
    Private.pending.get(this.cid_)?.reject('closing');
    Private.pending.delete(this.cid_);
    this.base?.disposed?.disconnect(this._base_disposed, this);
    if ((this.base as any)?.ipylabDisposeOnClose ?? this.get('auto_dispose')) {
      this.set('auto_dispose', false);
      this.base?.dispose();
    }
    return super.close(comm_closed);
  }

  async getObject(): Promise<IObservableDisposable> {
    // This is async for overloading
    return Private.connections.get(this.cid_);
  }

  ensurePending() {
    const cid = this.get('cid');
    if (!Private.pending.has(cid)) {
      Private.pending.set(cid, new PromiseDelegate());
    }
    const pc = Private.pending.get(cid);
    if (Private.connections.has(cid)) {
      pc.resolve(null);
    }
    return pc;
  }

  /**
   * Keep a reference to an object so it can be found from the backend.
   * Also keeps a reverse mapping for the last registered cid of the object
   * see: `IpylabModel.get_cid`

   * @param obj
   */
  static registerConnection(cid: string, obj: any) {
    if (!cid) {
      throw new Error('`cid` not provided!');
    }
    if (typeof obj !== 'object') {
      throw new Error(`An object is required but got a '${typeof obj}'`);
    }
    while (obj?.isConnectionModel) {
      obj = obj.base;
    }
    if (obj?.isDisposed) {
      throw new Error('object is disposed');
    }
    if (Private.connections.has(cid) && Private.connections.get(cid) !== obj) {
      throw new Error(`Another object is already registered for cid: ${cid}`);
    }
    ConnectionModel.ensureObservableDisposable(obj);
    obj.disposed.connect(() => {
      Private.connections.delete(cid);
      Private.connections_rev.delete(obj);
    });
    Private.connections.set(cid, obj);
    Private.connections_rev.set(obj, cid);
    if (Private.pending.has(cid)) {
      Private.pending.get(cid).resolve(null);
      Private.pending.delete(cid);
    }
    return obj;
  }

  /**
   * Modify the object to make it usable as an IObservableDisposable.
   * @param obj The object to modify.
   * @returns
   */
  static ensureObservableDisposable(obj: any) {
    if (typeof obj !== 'object') {
      throw new Error(`An object is required but got ${typeof obj} `);
    }
    if (obj.disposed) {
      // Assume obj provides an IObservableDisposable interface.
      return;
    }
    const args = { enumerable: false, configurable: true, writable: false };
    if (!obj.dispose) {
      Object.defineProperties(obj, {
        dispose: { value: () => null as any, ...args },
        ipylabDisposeOnClose: { value: true, ...args }
      });
    }
    const disposed = new Signal<any, null>(obj);
    const dispose_ = obj.dispose.bind(obj);
    const dispose = () => {
      if (obj.isDisposed) {
        return;
      }
      dispose_();
      disposed.emit(null);
      Signal.clearData(obj);
      if (!obj.isDisposed) {
        obj.isDisposed = true;
      }
    };
    Object.defineProperties(obj, {
      dispose: { value: dispose.bind(obj), ...args },
      disposed: { value: disposed, ...args }
    });
  }

  static get_cid(obj: any, register = false): string | null {
    if (register && !Private.connections_rev.has(obj)) {
      const cls =
        obj instanceof Widget &&
        obj.id &&
        ConnectionModel.getLuminoWidgetFromShell(obj.id)
          ? 'ShellConnection'
          : 'Connection';
      const cid = ConnectionModel.new_cid(cls);
      ConnectionModel.registerConnection(cid, obj);
    }
    return Private.connections_rev.get(obj);
  }

  static getConnection(cid: string): IObservableDisposable | undefined {
    return Private.connections.get(cid);
  }

  /**
   * Get the lumino widget from the shell using its id.
   *
   * @param id
   * @returns
   */
  static getLuminoWidgetFromShell(id: string): Widget | null {
    for (const area of [
      'main',
      'header',
      'top',
      'menu',
      'left',
      'right',
      'bottom'
    ]) {
      for (const widget of IpylabModel.labShell.widgets(
        area as ILabShell.Area
      )) {
        if (widget.id === id) {
          return widget;
        }
      }
    }
  }

  static new_cid(cls: string): string {
    const _PREFIX = 'ipylab-';
    const _SEP = '|';

    return `${_PREFIX}${cls}${_SEP}${UUID.uuid4()}`;
  }
  // 'cid' is used by BackboneJS so we use cid_ here.
  cid_: string;
  readonly isConnectionModel = true;
}

/**
 * A connection for widgets in the Shell.
 */
export class ShellConnectionModel extends ConnectionModel {
  /*
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ShellConnectionModel' };
  }

  async getObject(): Promise<Widget> {
    let base = Private.connections.get(this.cid_);
    if (!base && !Private.pending.has(this.cid_)) {
      const pending = this.ensurePending();
      IpylabModel.tracker.restored.then(() => {
        if (!Private.connections.has(this.cid_)) {
          setTimeout(
            () => pending.reject(`Shell connection not found ${this.cid_}`),
            10000
          );
        }
      });
    }
    await Private.pending.get(this.cid_)?.promise;
    base = Private.connections.get(this.cid_);
    if (!(base instanceof Widget)) {
      this.error(`Failed to locate a widget cid=${this.cid_}`);
    }
    return base;
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'activate':
        return IpylabModel.app.shell.activateById(this.base.id);
      default:
        return await super.operation(op, payload);
    }
  }
}

IpylabModel.ConnectionModel = ConnectionModel;

/**
 * A namespace for private data
 */
namespace Private {
  export const pending = new Map<string, PromiseDelegate<null>>();
  export const connections = new Map<string, IObservableDisposable>();
  export const connections_rev = new Map<IObservableDisposable, string>();
}
