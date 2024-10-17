// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { PromiseDelegate } from '@lumino/coreutils';
import { IpylabModel, Widget } from './ipylab';
import { listProperties } from './utils';

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
  async ipylabInit(base: any = null) {
    this.on('change:_dispose', this.disposeBase, this);
    const cid = this.get('cid');
    const id = this.get('id') ?? '';

    try {
      base = await this.fromConnectionOrId(cid, id);
      base.disposed.connect(() => this.close(null, true));
      await super.ipylabInit(base);
      base = ConnectionModel.registerConnection(cid, base);
    } catch (e) {
      console.log(
        'Failed to establish connection for cid="%s" id="%s "',
        cid,
        id
      );
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
    if (this.pending.has(cid)) {
      await this.pending.get(cid)?.promise;
    }
    this.base?.dispose();
  }

  get pending() {
    return IpylabModel.pendingShellConnections;
  }

  /**
   *
   * @param cid Get an object that has been registered as a connection.
   * @returns
   */
  async fromConnectionOrId(cid: string, id = ''): Promise<any> {
    if (IpylabModel.connections.has(cid)) {
      return IpylabModel.connections.get(cid);
    }
    if (id.slice(0, 10) === 'IPY_MODEL_') {
      const model_id = id.slice(10);
      return await IpylabModel.getWidgetModel(model_id);
    } else {
      return IpylabModel.getLuminoWidgetFromShell(id || cid);
    }
  }

  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ConnectionModel' };
  }
  readonly isConnectionModel = true;
}

/**
 * A connection for widgets in the Shell.
 */
export class ShellConnectionModel extends ConnectionModel {
  async fromConnectionOrId(cid: string, id = ''): Promise<Widget> {
    let base = await super.fromConnectionOrId(cid, id);
    if (!base) {
      if (!this.pending.has(cid)) {
        this.pending.set(cid, new PromiseDelegate());

        setTimeout(() => {
          IpylabModel.tracker.restored.then(() => {
            this.pending.get(cid)?.reject(`Shell connection not found ${cid}`);
            this.pending.delete(cid);
          });
        }, 10000);
      }

      await this.pending.get(cid).promise;
      base = await this.fromConnectionOrId(cid, id);
    }
    if (!(base instanceof Widget)) {
      throw new Error(
        `Failed to locate a widget. Got: ${JSON.stringify(listProperties(base))}`
      );
    }
    return base;
  }

  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ShellConnectionModel' };
  }
}
