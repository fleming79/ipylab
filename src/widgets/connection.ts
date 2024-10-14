// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { PromiseDelegate } from '@lumino/coreutils';
import { IpylabModel } from './ipylab';

/**
 * Provides a connection from any object reachable here to one or more Python backends.
 *
 * Typically the object is registered first via the method `registerConnection` with a cid
 * In Python The `cid` is passed when creating a new Connection.
 *
 * The object is set as the base. If the object is disposable, the ConnectionModel will
 * also close when the object is disposed.
 */
export class ConnectionModel extends IpylabModel {
  async ipylabInit() {
    this.on('change:_dispose', this.disposeBase, this);
    const cid = this.get('cid');
    const id = this.get('id') ?? '';
    try {
      let base;
      try {
        base = await ConnectionModel.fromConnectionOrId(cid, id);
      } catch {
        if (!IpylabModel.pendingConnections.has(cid)) {
          IpylabModel.pendingConnections.set(cid, new PromiseDelegate());
        }
        await IpylabModel.pendingConnections.get(cid).promise;
        base = await ConnectionModel.fromConnectionOrId(cid, id);
      }
      while (base?.isConnectionModel) {
        base = base.base;
      }
      base.disposed.connect(() => this.close(null, true));
      await super.ipylabInit(base);
      ConnectionModel.registerConnection(cid, base);
    } catch (e) {
      console.log(
        'Failed to establish connection for cid="%s" id="%s "',
        cid,
        id
      );
      if (IpylabModel.pendingConnections.has(cid)) {
        IpylabModel.pendingConnections.get(cid).reject(e);
        IpylabModel.pendingConnections.delete(cid);
      }
      this.close();
      throw e;
    }
  }

  close(comm_closed?: boolean, base_closed?: boolean): Promise<void> {
    if (!base_closed && (this.base as any)?.ipylabDisposeOnClose) {
      this.disposeBase();
    }
    return super.close((comm_closed || this.get('_dispose')) ?? false);
  }

  async disposeBase() {
    const cid = this.get('cid');
    if (IpylabModel.pendingConnections.has(cid)) {
      await IpylabModel.pendingConnections.get(cid)?.promise;
    }
    this.base?.dispose();
  }

  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ConnectionModel' };
  }
  readonly isConnectionModel = true;
}
