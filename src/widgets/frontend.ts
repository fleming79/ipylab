// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { KernelWidgetManager } from '@jupyter-widgets/jupyterlab-manager';
import type { Kernel } from '@jupyterlab/services';
import { PromiseDelegate } from '@lumino/coreutils';
import { IpylabAutostart } from './autostart';
import { IpylabModel } from './ipylab';

export class JupyterFrontEndModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'JupyterFrontEndModel' };
  }
  async ipylabInit(base: any = null) {
    this.set('version', JFEM.app.version);
    JFEM.sessionManager.runningChanged.connect(this.updateAllSessions, this);
    if (JFEM.labShell) {
      JFEM.labShell.currentChanged.connect(this.updateSessionInfo, this);
      JFEM.labShell.activeChanged.connect(this.updateSessionInfo, this);
      this.updateSessionInfo();
    }
    this.updateAllSessions();

    if (!Private.jfemPromises.has(this.kernel.id)) {
      Private.jfemPromises.set(this.kernel.id, new PromiseDelegate());
    }
    if (!Private.vpathTojfem.has(this.vpath)) {
      Private.vpathTojfem.set(this.vpath, new PromiseDelegate());
    }
    Private.vpathTojfem.get(this.vpath).resolve(this);
    await super.ipylabInit(base);
    Private.jfemPromises.get(this.kernel.id).resolve(this);
  }

  close(comm_closed?: boolean): Promise<void> {
    Private.jfemPromises.delete(this.kernel.id);
    Private.vpathTojfem.delete(this.vpath);
    JFEM.labShell.currentChanged.disconnect(this.updateSessionInfo, this);
    JFEM.labShell.activeChanged.disconnect(this.updateSessionInfo, this);
    JFEM.sessionManager.runningChanged.disconnect(this.updateAllSessions, this);
    return super.close(comm_closed);
  }

  get vpath() {
    let vpath = this.get('vpath');
    if (!vpath) {
      const cs = this.get('current_session');
      if (cs?.kernel?.id === this.kernel.id) {
        vpath = cs?.path;
      }
      if (!vpath) {
        for (const session of JFEM.sessionManager.running()) {
          if (session.kernel.id === this.kernel.id) {
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

  private updateSessionInfo(): void {
    const currentWidget = JFEM.app.shell.currentWidget as any;
    const current_session = currentWidget?.sessionContext?.session?.model ?? {};
    if (this.get('current_widget_id') !== currentWidget?.id) {
      this.set('current_widget_id', currentWidget?.id ?? '');
      this.set('current_session', current_session);
      this.save_changes();
    }
  }
  private updateAllSessions(): void {
    this.set('all_sessions', Array.from(JFEM.sessionManager.running()));
    this.save_changes();
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'evaluate':
        return await this.scheduleOperation('evaluate', payload, 'auto');
      case 'checkstartIyplabKernel':
        return (await IpylabAutostart.checkStart(
          payload.restart ?? false
        )) as any;
      case 'shutdownKernel':
        if (payload.vpath) {
          if (Private.jfemPromises.has(payload.vpath)) {
            await JFEM.getModel(payload.vpath).then(jfem =>
              jfem.kernel.shutdown()
            );
          }
        } else {
          this.kernel.shutdown();
        }
        return null;
      case 'ipylab_kernel_ready':
        return JFEM.ipylabKernelReady.resolve(payload.init_count === 0);
      default:
        return await super.operation(op, payload);
    }
  }

  /**
   * Ensure the JupyterFrontendModel 'app' is running in the kernel.
   * @param kernel
   */
  static async ensureFrontend(kernel: Kernel.IKernelConnection, vpath = '') {
    if (!Private.jfemPromises.has(kernel.id)) {
      const manager = new KernelWidgetManager(kernel, IpylabModel.rendermime);
      Private.jfemPromises.set(kernel.id, new PromiseDelegate());
      await kernel.requestExecute(
        {
          code: `
            import ipylab
            ipylab.Ipylab._hook.start_app(vpath='${vpath}')`,
          store_history: false
        },
        true
      ).done;
      if (!manager.restoredStatus) {
        await new Promise(resolve => manager.restored.connect(resolve));
      }
    }
    return await Private.jfemPromises.get(kernel.id).promise;
  }

  static async getModel(vpath: string) {
    if (!vpath || typeof vpath !== 'string') {
      throw new Error(`Invalid vpath ${vpath}`);
    }
    if (!Private.vpathTojfem.has(vpath)) {
      Private.vpathTojfem.set(vpath, new PromiseDelegate());
      // const model = await JFEM.JFEM.sessionManager.findByPath(vpath);
      // if (model) {
      //   const kernel = JFEM.kernelManager.connectTo({
      //     model: model.kernel
      //   });
      //   JFEM.ensureFrontend(kernel);
      // } else {
      // }
      JFEM.newSessionContext(vpath);
    }
    return await Private.vpathTojfem.get(vpath).promise;
  }

  static async openConsole(args: any) {
    const currentWidget = JFEM.tracker.currentWidget;
    const ipylabSettings = (currentWidget as any)?.ipylabSettings;
    const jfem = await JFEM.getModel(ipylabSettings.vpath);
    const payload = { cid: ipylabSettings.cid, ...args };
    return await jfem.scheduleOperation('open_console', payload, 'auto');
  }
}

IpylabModel.JFEM = JupyterFrontEndModel;
const JFEM = JupyterFrontEndModel;

/**
 * A namespace for private data
 */
namespace Private {
  export const vpathTojfem = new Map<
    string,
    PromiseDelegate<JupyterFrontEndModel>
  >();

  /**
   * Promises to frontends that may be loading.
   */
  export const jfemPromises = new Map<
    string,
    PromiseDelegate<JupyterFrontEndModel>
  >();
}
