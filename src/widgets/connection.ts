// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { PromiseDelegate, UUID } from '@lumino/coreutils';
import { Signal } from '@lumino/signaling';
import { IpylabModel } from './ipylab';
import { IObservableDisposable } from '@lumino/disposable';
import { Widget } from '@lumino/widgets';

/**
 * ConnectionModel provides a connection to an object using a unique 'cid'.
 *
 * The object to be referenced must first be registered static method
 * `ConnectionModel.registerConnection`.
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
    base = await this.getObject();
    if (!base) {
      this.close();
      return;
    }
    base.disposed.connect(this._base_disposed, this);
    await super.ipylabInit(base);
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
        ConnectionModel.ShellModel.getLuminoWidgetFromShell(obj.id)
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
   * Get the session associated with the lumino widget if it has one.
   */
  static async getSession(widget: Widget) {
    const path = (widget as any)?.ipylabSettings?.vpath;
    if (path) {
      return await ConnectionModel.sessionManager.findByPath(path);
    }
    return (widget as any)?.sessionContext?.session?.model ?? {};
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
 * A connection to widgets in the Shell.
 */
export class ShellConnectionModel extends ConnectionModel {
  /*
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ShellConnectionModel' };
  }

  async getObject() {
    if (
      !Private.connections.has(this.cid_) &&
      !Private.pending.has(this.cid_)
    ) {
      const pending = new PromiseDelegate<null>();
      Private.pending.set(this.cid_, pending);
      IpylabModel.tracker.restored.then(() => {
        if (!Private.connections.has(this.cid_)) {
          setTimeout(() => pending.resolve(null), 10000);
        }
      });
    }
    await Private.pending.get(this.cid_)?.promise;
    return Private.connections.get(this.cid_);
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'activate':
        return IpylabModel.app.shell.activateById(this.base.id);
      case 'getSession':
        return ShellConnectionModel.getSession(this.base);
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
