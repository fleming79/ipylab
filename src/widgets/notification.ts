// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { Notification } from '@jupyterlab/apputils';
import { ObservableDisposableDelegate } from '@lumino/disposable';
import { IpylabModel } from './ipylab';
/**
 * The model for a notification.
 */
export class NotificationManagerModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'NotificationManagerModel'
    };
  }

  async ipylabInit(base: any = null) {
    Notification.manager.changed.connect(this.update, this);
    await super.ipylabInit(Notification);
  }

  close(comm_closed?: boolean): Promise<void> {
    Notification.manager.changed.disconnect(this.update, this);
    return super.close(comm_closed);
  }

  update() {
    for (const id of this.notifications.keys()) {
      if (!Notification.manager.has(id)) {
        const obj = this.notifications.get(id);
        if (obj) {
          obj.dispose();
        }
        this.notifications.delete(id);
      }
    }
  }

  notification(payload: any) {
    const { message, type, options } = payload;
    const id = Notification.manager.notify(message, type, options);
    const obj = new ObservableDisposableDelegate(() =>
      Notification.manager.dismiss(id)
    ) as any;
    obj.id = id;
    this.notifications.set(id, obj);
    return obj;
  }

  createAction(payload: any) {
    const action = { ...payload } as any;
    const cid = action.cid;
    action.callback = (event: MouseEvent) => {
      if (action.keep_open) {
        event.preventDefault();
      }
      return this.scheduleOperation('action_callback', { cid }, 'done');
    };
    return action;
  }

  notifications = new Map<string, ObservableDisposableDelegate>();
}
