// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { PromiseDelegate, UUID } from '@lumino/coreutils';
import { IObservableDisposable, IpylabModel, Widget } from './ipylab';
import { ensureObservableDisposable } from './utils';

// Constants used for cid
const _PREFIX = 'ipylab-';
const _SEP = '|';

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
    this.on('change:_dispose', this.disposeBase, this);
    const cid = this.get('cid');

    try {
      base = await this.getObject(cid);
      base.disposed.connect(() => {
        this.set('auto_dispose', false);
        this.close(null);
      });
      await super.ipylabInit(base);
    } catch (e) {
      ConnectionModel.pendingConnections.delete(cid);
      this.close();
      this.error(`Failed to establish connection for cid=${cid}!\n${e}`);
    }
  }

  close(comm_closed = false): Promise<void> {
    if ((this.base as any)?.ipylabDisposeOnClose || this.get('auto_dispose')) {
      this.disposeBase();
    }
    return super.close(comm_closed);
  }

  private async disposeBase() {
    await this.pendingObj?.promise;
    this.set('auto_dispose', false);
    this.base?.dispose();
  }

  async getObject(cid: string): Promise<any> {
    return ConnectionModel.connections.get(cid);
  }
  get pendingObj() {
    return ConnectionModel.pendingConnections.get(this.get('cid'));
  }

  ensurePending() {
    const cid = this.get('cid');
    if (!ConnectionModel.pendingConnections.has(cid)) {
      ConnectionModel.pendingConnections.set(cid, new PromiseDelegate());
    }
    const pc = ConnectionModel.pendingConnections.get(cid);
    if (ConnectionModel.connections.has(cid)) {
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
      throw new Error(`object is disposed`);
    }
    if (
      ConnectionModel.connections.has(cid) &&
      ConnectionModel.connections.get(cid) !== obj
    ) {
      throw new Error(`Another object is already registered for cid: ${cid}`);
    }
    ensureObservableDisposable(obj);
    obj.disposed.connect(() => {
      ConnectionModel.connections.delete(cid);
      ConnectionModel.connections_rev.delete(obj);
    });
    ConnectionModel.connections.set(cid, obj);
    ConnectionModel.connections_rev.set(obj, cid);
    if (ConnectionModel.pendingConnections.has(cid)) {
      ConnectionModel.pendingConnections.get(cid).resolve(null);
      ConnectionModel.pendingConnections.delete(cid);
    }
    return obj;
  }

  static get_cid(obj: any, register = false): string | null {
    if (register && !ConnectionModel.connections_rev.has(obj)) {
      const cls =
        obj instanceof Widget &&
        obj.id &&
        ConnectionModel.getLuminoWidgetFromShell(obj.id)
          ? 'ShellConnection'
          : 'Connection';
      const cid = `${_PREFIX}${cls}${_SEP}${UUID.uuid4()}`;
      ConnectionModel.registerConnection(cid, obj);
    }
    return ConnectionModel.connections_rev.get(obj);
  }

  readonly isConnectionModel = true;

  public static connections = new Map<string, IObservableDisposable>();
  public static connections_rev = new Map<IObservableDisposable, string>();
  public static pendingConnections = new Map<string, PromiseDelegate<null>>();
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

  async getObject(cid: string): Promise<Widget> {
    let base = ConnectionModel.connections.get(cid);
    if (!base && !this.pendingObj) {
      const pending = this.ensurePending();
      IpylabModel.tracker.restored.then(() => {
        if (!ConnectionModel.connections.has(cid)) {
          setTimeout(
            () => pending.reject(`Shell connection not found ${cid}`),
            10000
          );
        }
      });
    }
    await this.pendingObj?.promise;
    base = ConnectionModel.connections.get(cid);
    if (!(base instanceof Widget)) {
      this.error(`Failed to locate a widget cid=${cid}`);
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
