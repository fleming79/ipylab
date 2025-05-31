// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { PromiseDelegate, UUID } from '@lumino/coreutils';
import { Signal } from '@lumino/signaling';
import { IpylabModel } from './ipylab';
import { IObservableDisposable } from '@lumino/disposable';
import { Widget } from '@lumino/widgets';

/**
 * ConnectionModel provides a connection to an object using a unique 'connection_id'.
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
    this.connection_id = this.get('connection_id');
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
    Private.pending.get(this.connection_id)?.reject('closing');
    Private.pending.delete(this.connection_id);
    this.base?.disposed?.disconnect(this._base_disposed, this);
    if ((this.base as any)?.ipylabDisposeOnClose ?? this.get('auto_dispose')) {
      this.set('auto_dispose', false);
      this.base?.dispose();
    }
    return super.close(comm_closed);
  }

  async getObject(): Promise<IObservableDisposable> {
    // This is async for overloading
    return Private.connections.get(this.connection_id);
  }

  /**
   * Keep a reference to an object so it can be found from the backend.
   * Also keeps a reverse mapping for the last registered connection_id of the object
   * see: `IpylabModel.get_cid`

   * @param obj
   */
  static registerConnection(connection_id: string, obj: any) {
    if (!connection_id) {
      throw new Error('`connection_id` not provided!');
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
    if (
      Private.connections.has(connection_id) &&
      Private.connections.get(connection_id) !== obj
    ) {
      throw new Error(
        `Another object is already registered for connection_id: ${connection_id}`
      );
    }
    ConnectionModel.ensureObservableDisposable(obj);
    obj.disposed.connect(() => {
      Private.connections.delete(connection_id);
      Private.connections_rev.delete(obj);
    });
    Private.connections.set(connection_id, obj);
    Private.connections_rev.set(obj, connection_id);
    if (Private.pending.has(connection_id)) {
      Private.pending.get(connection_id).resolve(null);
      Private.pending.delete(connection_id);
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
      const connection_id = ConnectionModel.new_cid(cls);
      ConnectionModel.registerConnection(connection_id, obj);
    }
    return Private.connections_rev.get(obj);
  }

  static getConnection(
    connection_id: string
  ): IObservableDisposable | undefined {
    return Private.connections.get(connection_id);
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

  // 'connection_id' is used by BackboneJS so we use connection_id here.
  connection_id: string;
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
      !Private.connections.has(this.connection_id) &&
      !Private.pending.has(this.connection_id)
    ) {
      const pending = new PromiseDelegate<null>();
      Private.pending.set(this.connection_id, pending);
      IpylabModel.tracker.restored.then(() => {
        if (!Private.connections.has(this.connection_id)) {
          setTimeout(() => pending.resolve(null), 10000);
        }
      });
    }
    await Private.pending.get(this.connection_id)?.promise;
    return Private.connections.get(this.connection_id);
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
