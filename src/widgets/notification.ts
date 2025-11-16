// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { Notification } from '@jupyterlab/apputils';
import { ObservableDisposable } from '../observable_disposable';
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

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'update':
        return this.base.update(payload.args);
      case 'notification':
        return this.notification(payload);
      case 'createAction':
        return this.createAction(payload);
      default:
        return await super.operation(op, payload);
    }
  }

  notification(payload: any) {
    const { message, type, options } = payload;
    const id = this.base.notify(message, type, options);
    return new NotifyLink(id);
  }

  createAction(payload: any) {
    const action = { ...payload } as any;
    const connection_id = action.connection_id;
    action.callback = (event: MouseEvent) => {
      if (action.keep_open) {
        event.preventDefault();
      }
      return this.scheduleOperation(
        'action_callback',
        { connection_id },
        'auto'
      );
    };
    return action;
  }

  public readonly base: typeof Notification.manager;
}

/**
 * A small object to keep track of a notification in the notification manager by its id.
 *
 * It will dispose itself once the manager no longer 'has' the id registered.
 */
class NotifyLink extends ObservableDisposable {
  constructor(public id: string = '') {
    super();
    this.id = id;
    this.manager.changed.connect(this._check_exists, this);
  }

  get manager() {
    return IpylabModel.Notification.manager;
  }

  _check_exists() {
    if (!this.manager.has(this.id)) {
      this.dispose();
    }
  }

  dispose(): void {
    if (this.isDisposed) {
      return;
    }
    this.manager.changed.disconnect(this._check_exists, this);
    IpylabModel.Notification.manager.dismiss(this.id);
    super.dispose();
  }
}
