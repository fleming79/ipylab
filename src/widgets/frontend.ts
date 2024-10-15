// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import {
  InputDialog,
  MainAreaWidget,
  showDialog,
  showErrorMessage
} from '@jupyterlab/apputils';
import { FileDialog } from '@jupyterlab/filebrowser';
import { IMainMenu, MainMenu } from '@jupyterlab/mainmenu';
import { PromiseDelegate, UUID } from '@lumino/coreutils';
import { IpylabAutostart } from './autostart';
import { IpylabModel, Widget } from './ipylab';
import { listProperties } from './utils';

export class JupyterFrontEndModel extends IpylabModel {
  async ipylabInit(base: any = null) {
    if (!IpylabModel.jfemPromises.has(this.kernelId)) {
      IpylabModel.jfemPromises.set(this.kernelId, new PromiseDelegate());
    }
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
    await super.ipylabInit(base);
    IpylabModel.jfemPromises.get(this.kernelId).resolve(this);
  }

  close(comm_closed?: boolean): Promise<void> {
    IpylabModel.jfemPromises.delete(this.kernelId);
    this.labShell.currentChanged.disconnect(this._updateSessionDetails, this);
    this.labShell.activeChanged.disconnect(this._updateSessionDetails, this);
    this.sessionManager.runningChanged.disconnect(
      this._updateAllSessionDetails,
      this
    );
    return super.close(comm_closed);
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
        if (payload.kernelId) {
          await this.commands.execute('kernelmenu:shutdown', {
            id: payload.kernelId
          });
        } else {
          this.kernel.shutdown();
        }
        return null;
      case 'addToShell':
        return await this.addToShell(payload);
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

  /**
   * Provided for IpylabModel.tracker for restoring widgets to the shell.
   * @param args `ipylabSettings` in 'addToShell'
   */
  static async restoreToShell(args: any) {
    // Wait for backend to load/reload plugins.

    const freshLoad = await IpylabModel.ipylabKernelReady.promise;
    if (freshLoad && IpylabModel.jfemPromises.size <= 1 && !args.evaluate) {
      return;
    }
    const jfem = await IpylabModel.getFrontendModel(args);
    await jfem.addToShell(args);
  }

  /**
   * Add a widget to the application shell.
   *
   * This function can handle ipywidgets and native Widgets and  be used to move
   * widgets about the shell.
   *
   * Ipywidgets are added to a tracker enabling restoration from a
   * running kernel such as page refreshing and switching workspaces.
   *
   * Generative widget creation is supported with 'evaluate' using the same
   * code as 'evalute'. The evaluated code must return a widget to be valid.
   *
   * @param args An object with area, options, cid, id, kernelId & evaluate.
   */
  async addToShell(args: any): Promise<Widget> {
    let jfem = this as JupyterFrontEndModel;
    if (!args.id && args.evaluate) {
      jfem = await IpylabModel.getFrontendModel(args);
    }
    return await jfem._addToShell(args);
  }

  async _addToShell(args: any): Promise<Widget> {
    let luminoWidget: Widget | MainAreaWidget;
    if (IpylabModel.connections.has(args.cid)) {
      luminoWidget = await IpylabModel.fromConnectionOrId(args.cid);
      if (!(luminoWidget instanceof Widget)) {
        throw new Error(`Not a Widget ${listProperties(luminoWidget)}`);
      }
    } else {
      try {
        try {
          luminoWidget = await IpylabModel.toLuminoWidget(args);
          // Create a new lumino widget
        } catch (e) {
          if (args.evaluate) {
            args.id = await this.scheduleOperation('evaluate', args, 'raw');
            luminoWidget = await IpylabModel.toLuminoWidget(args);
            // Overwrite kernel ID as this is where evaluation should occur.
            args.kernelId = this.kernelId;
          } else {
            throw e;
          }
        }
        if (!(luminoWidget instanceof Widget)) {
          if (!args.id) {
            throw new Error(
              `Unable to create a lumino widget using these args: ${JSON.stringify(args)}`
            );
          }
        }
      } catch (e) {
        IpylabModel.pendingConnections.get(args.cid)?.reject(e);
        throw e;
      }
      IpylabModel.registerConnection(args.cid, luminoWidget);
    }
    args.area = args.area || 'main';
    if (
      (args.area === 'main' && !(luminoWidget instanceof MainAreaWidget)) ||
      typeof luminoWidget.title === 'undefined'
    ) {
      // Wrap the widget with a MainAreaWidget
      const w = (luminoWidget = new MainAreaWidget({ content: luminoWidget }));
      w.node.removeChild(w.toolbar.node);
      w.addClass('ipylab-MainArea');
    }
    args.cid = args.cid || `ipylab-shell-connection:${UUID.uuid4()}`;
    luminoWidget.id = luminoWidget.id || args.id || args.cid;
    IpylabModel.app.shell.add(luminoWidget as any, args.area, args.options);

    // Register widgets originating from IpyWidgets or evaluate
    if (args.isIpyWidget || args.evaluate) {
      // The property `isIpyWidget`is added in `toLuminoWidget`
      args.kernelId = args.kernelId || this.kernelId;
      if (!args.path) {
        for (const session of IpylabModel.sessionManager.running()) {
          if (session.kernel.id === args.kernelId) {
            args.path = session.path;
            break;
          }
        }
      }

      if (!IpylabModel.tracker.has(luminoWidget)) {
        (luminoWidget as any).ipylabSettings = args;
        IpylabModel.tracker.add(luminoWidget);
      } else {
        delete args.cid;
        Object.assign((luminoWidget as any).ipylabSettings, args);
        IpylabModel.tracker.save(luminoWidget);
      }
    }
    return luminoWidget;
  }

  static async openConsole(args: any) {
    const currentWidget = IpylabModel.tracker.currentWidget;
    const args_ = (currentWidget as any)?.ipylabSettings;
    const jfem = await IpylabModel.getFrontendModel(args_);
    return await jfem.scheduleOperation(
      'open console',
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
