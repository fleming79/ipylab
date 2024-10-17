// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import {
  InputDialog,
  showDialog,
  showErrorMessage
} from '@jupyterlab/apputils';
import { FileDialog } from '@jupyterlab/filebrowser';
import { IMainMenu, MainMenu } from '@jupyterlab/mainmenu';
import { PromiseDelegate } from '@lumino/coreutils';
import { IObservableDisposable } from '@lumino/disposable';
import { IpylabAutostart } from './autostart';
import { IpylabModel } from './ipylab';

export class JupyterFrontEndModel extends IpylabModel {
  async ipylabInit(base: any = null) {
    this.set('version', this.app.version);
    this.sessionManager.runningChanged.connect(
      this._updateAllSessionDetails,
      this
    );
    if (this.labShell) {
      this.labShell.currentChanged.connect(this._updateSessionDetails, this);
      this.labShell.activeChanged.connect(this._updateSessionDetails, this);
      this._updateSessionDetails();
    }
    this._updateAllSessionDetails();

    if (!IpylabModel.jfemPromises.has(this.kernelId)) {
      IpylabModel.jfemPromises.set(this.kernelId, new PromiseDelegate());
    }
    if (!Private.vpathTojfem.has(this.vpath)) {
      Private.vpathTojfem.set(this.vpath, new PromiseDelegate());
    }
    IpylabModel.jfemPromises.get(this.kernelId).resolve(this);
    Private.vpathTojfem.get(this.vpath).resolve(this);
    await super.ipylabInit(base);
  }

  close(comm_closed?: boolean): Promise<void> {
    IpylabModel.jfemPromises.delete(this.kernelId);
    Private.vpathTojfem.delete(this.vpath);
    this.labShell.currentChanged.disconnect(this._updateSessionDetails, this);
    this.labShell.activeChanged.disconnect(this._updateSessionDetails, this);
    this.sessionManager.runningChanged.disconnect(
      this._updateAllSessionDetails,
      this
    );
    return super.close(comm_closed);
  }

  get vpath() {
    let vpath = this.get('vpath');
    if (!vpath) {
      const cs = this.get('current_session');
      if (cs?.kernel?.id === this.kernelId) {
        vpath = cs?.path;
      }
      if (!vpath) {
        for (const session of IpylabModel.sessionManager.running()) {
          if (session.kernel.id === this.kernelId) {
            vpath = session.path;
            break;
          }
        }
      }
      this.set('vpath', vpath);
      this.save_changes();
    }
    return vpath;
  }

  private _updateSessionDetails(): void {
    const currentWidget = this.shell.currentWidget as any;
    const current_session = currentWidget?.sessionContext?.session?.model ?? {};
    if (this.get('current_widget_id') !== currentWidget?.id) {
      this.set('current_widget_id', currentWidget?.id ?? '');
      this.set('current_session', current_session);
      this.save_changes();
    }
  }
  private _updateAllSessionDetails(): void {
    this.set('all_sessions', Array.from(this.sessionManager.running()));
    this.save_changes();
  }

  async operation(op: string, payload: any): Promise<any> {
    function _get_result(result: any): any {
      if (result.value === null) {
        throw new Error('Cancelled');
      }
      return result.value;
    }
    let result;
    switch (op) {
      case 'showDialog':
        result = await showDialog(payload);
        return { value: result.button.accept, isChecked: result.isChecked };
      case 'getBoolean':
        return await InputDialog.getBoolean(payload).then(_get_result);
      case 'getItem':
        return await InputDialog.getItem(payload).then(_get_result);
      case 'getNumber':
        return await InputDialog.getNumber(payload).then(_get_result);
      case 'getText':
        return await InputDialog.getText(payload).then(_get_result);
      case 'getPassword':
        return await InputDialog.getPassword(payload).then(_get_result);
      case 'showErrorMessage':
        return await showErrorMessage(
          payload.title,
          payload.error,
          payload.buttons
        );
      case 'getOpenFiles':
        payload.manager = this.defaultBrowser.model.manager;
        return await FileDialog.getOpenFiles(payload).then(_get_result);
      case 'getExistingDirectory':
        payload.manager = this.defaultBrowser.model.manager;
        return await FileDialog.getExistingDirectory(payload).then(_get_result);
      case 'generateMenu':
        return this._generateMenu(payload.options);
      case 'evaluate':
        // return await JupyterFrontEndModel.evaluate(payload);
        return await this.scheduleOperation('evaluate', payload, 'raw');
      case 'checkstartIyplabKernel':
        return (await IpylabAutostart.checkStart(
          payload.restart ?? false
        )) as any;
      case 'shutdownKernel':
        if (payload.vpath) {
          if (IpylabModel.jfemPromises.has(payload.vpath)) {
            await JupyterFrontEndModel.getModel(payload.vpath).then(jfem =>
              jfem.kernel.shutdown()
            );
          }
        } else {
          this.kernel.shutdown();
        }
        return null;
      case 'autostart_complete':
        return this.autostartComplete.resolve(null);
      case 'ipylab_kernel_ready':
        return IpylabModel.ipylabKernelReady.resolve(payload.init_count === 0);
      default:
        return await super.operation(op, payload);
    }
  }

  private _generateMenu(options: IMainMenu.IMenuOptions) {
    const menu = MainMenu.generateMenu(
      this.commands,
      options,
      this.translator.load('jupyterlab')
    );
    return menu;
  }

  static async getModel(vpath: string) {
    if (!vpath || typeof vpath !== 'string') {
      throw new Error(`Invalid vpath ${vpath}`);
    }
    if (!Private.vpathTojfem.has(vpath)) {
      Private.vpathTojfem.set(vpath, new PromiseDelegate());
      // const model = await IpylabModel.sessionManager.findByPath(vpath);
      // if (model) {
      //   const kernel = IpylabModel.kernelManager.connectTo({
      //     model: model.kernel
      //   });
      //   IpylabModel.ensureFrontend(kernel);
      // } else {
      // }
      IpylabModel.newSessionContext(vpath);
    }
    return await Private.vpathTojfem.get(vpath).promise;
  }

  static async openConsole(args: any) {
    const currentWidget = IpylabModel.tracker.currentWidget;
    const args_ = (currentWidget as any)?.ipylabSettings;
    const jfem = await JupyterFrontEndModel.getModel(args_.vpath);
    return await jfem.scheduleOperation(
      'open_console',
      { ...args_, ...args },
      'raw'
    );
  }

  isIpylabKernel: boolean;
  autostartComplete = new PromiseDelegate();

  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'JupyterFrontEndModel' };
  }
}

/**
 * A namespace for private data
 */
namespace Private {
  export const connections = new Map<string, IObservableDisposable>();
  export const vpathTojfem = new Map<
    string,
    PromiseDelegate<JupyterFrontEndModel>
  >();
}
