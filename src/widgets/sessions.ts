// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

// SessionManager exposes `app.serviceManager.sessions` to user python kernel

import { IpylabModel } from './ipylab';

/**
 * The model for a Session Manager
 */
export class SessionManagerModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): any {
    return { ...super.defaults(), _model_name: SessionManagerModel };
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'getCurrentSession':
        return await SessionManagerModel.ConnectionModel.getSession(
          IpylabModel.labShell.currentWidget
        );
      case 'getRunning':
        if (payload.refresh) {
          await IpylabModel.sessionManager.refreshRunning();
        }
        return Array.from(IpylabModel.sessionManager.running());
      default:
        return await super.operation(op, payload);
    }
  }
}
