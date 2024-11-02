// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { KernelWidgetManager } from '@jupyter-widgets/jupyterlab-manager';
import { SessionContext, SessionContextDialogs } from '@jupyterlab/apputils';
import { ILogger, ILoggerRegistry, IStateChange } from '@jupyterlab/logconsole';
import { PromiseDelegate } from '@lumino/coreutils';
import { IpylabModel, PER_KERNEL_WM } from './ipylab';

/**
 * JupyterFrontEndModel (JFEM) is a SINGLETON per kernel.
 */
export class JupyterFrontEndModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'JupyterFrontEndModel' };
  }

  initialize(attributes: any, options: any): void {
    super.initialize(attributes, options);
    this.logger = JFEM.loggerRegistry.getLogger(this.vpath);
    this.logger.stateChanged.connect(this.loggerStateChanged as any, this);
    Private.jfems.set(this.kernel.id, this);
  }

  async ipylabInit(base: any = null) {
    this.set('version', JFEM.app.version);
    this.set('per_kernel_widget_manager_detected', PER_KERNEL_WM);
    JFEM.sessionManager.runningChanged.connect(this.updateAllSessions, this);
    if (JFEM.labShell) {
      JFEM.labShell.currentChanged.connect(this.updateSessionInfo, this);
      JFEM.labShell.activeChanged.connect(this.updateSessionInfo, this);
      this.updateSessionInfo();
    }
    this.updateAllSessions();
    await super.ipylabInit(base);
    if (!Private.vpathTojfem.has(this.vpath)) {
      Private.vpathTojfem.set(this.vpath, new PromiseDelegate());
    }
    Private.vpathTojfem.get(this.vpath).resolve(this);
  }

  close(comm_closed?: boolean): Promise<void> {
    Private.jfems.delete(this.kernel.id);
    Private.vpathTojfem.delete(this.vpath);
    JFEM.labShell.currentChanged.disconnect(this.updateSessionInfo, this);
    JFEM.labShell.activeChanged.disconnect(this.updateSessionInfo, this);
    JFEM.sessionManager.runningChanged.disconnect(this.updateAllSessions, this);
    this.logger.stateChanged.disconnect(this.loggerStateChanged as any, this);
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

  private loggerStateChanged(sender: ILogger, change: IStateChange): void {
    if (this.get('logger_level') !== this.logger.level) {
      this.set('logger_level', this.logger.level);
      this.save_changes();
    }
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'evaluate':
        return await this.scheduleOperation('evaluate', payload, 'auto');
      case 'startIyplabKernel':
        return await JFEM.startIpylabKernel(payload.restart ?? false);
      case 'shutdownKernel':
        if (payload.vpath) {
          if (Private.vpathTojfem.has(payload.vpath)) {
            await JFEM.getModelByVpath(payload.vpath).then(jfem =>
              jfem.kernel.shutdown()
            );
          }
        } else {
          this.kernel.shutdown();
        }
        return null;
      default:
        return await super.operation(op, payload);
    }
  }

  static getModelByKernelId(kernelId: string) {
    return Private.jfems.get(kernelId);
  }

  /**
   * Get the JupyterFrontendModel for the vpath.
   * If the path doesn't exist, a new kernel will be started.
   * @param vpath The session path
   * @returns
   */
  static async getModelByVpath(vpath: string): Promise<JupyterFrontEndModel> {
    if (!vpath || typeof vpath !== 'string') {
      throw new Error(`Invalid vpath ${vpath}`);
    }
    if (!Private.vpathTojfem.has(vpath)) {
      if (!PER_KERNEL_WM) {
        throw new Error(
          'A per-kernel KernelWidgetManager is required to start a new session!'
        );
      }
      let kernel;
      Private.vpathTojfem.set(vpath, new PromiseDelegate());
      const model = await IpylabModel.sessionManager.findByPath(vpath);
      if (model) {
        kernel = IpylabModel.app.serviceManager.kernels.connectTo({
          model: model.kernel
        });
      } else {
        const sessionContext = new SessionContext({
          sessionManager: IpylabModel.sessionManager,
          specsManager: IpylabModel.app.serviceManager.kernelspecs,
          path: vpath,
          name: vpath,
          type: 'console',
          kernelPreference: { language: 'python' }
        });
        await sessionContext.initialize();
        if (!sessionContext.isReady) {
          await new SessionContextDialogs({
            translator: IpylabModel.translator
          }).selectKernel(sessionContext!);
        }
        if (!sessionContext.isReady) {
          sessionContext.dispose();
          throw new Error('Cancelling because a kernel was not provided');
        }
        kernel = sessionContext.session.kernel;
      }
      const wm = new KernelWidgetManager(kernel, IpylabModel.rendermime);
      if (!wm.restoredStatus) {
        await new Promise(resolve => wm.restored.connect(resolve));
      }
      if (!Private.jfems.has(kernel.id)) {
        kernel.requestExecute(
          {
            code: `
            import ipylab
            ipylab.plugin_manager.hook.start_app(vpath='${vpath}')`,
            store_history: false
          },
          true
        );
      }
    }
    return await new Promise((resolve, reject) => {
      const timeoutID = setTimeout(() => {
        const msg = `Failed to get a JupyterFrontendModel for vpath='${vpath}'`;
        Private.vpathTojfem.get(vpath).reject(msg);
        Private.vpathTojfem.delete(vpath);
        reject(msg);
      }, 10000);
      Private.vpathTojfem.get(vpath).promise.then(jfem => {
        clearTimeout(timeoutID);
        resolve(jfem);
      });
    });
  }

  /**
   * Get the WidgetModel
   *
   * This depends on the PR requiring a per-kernel widget manager.
   *
   * @param model_id The model id
   * @returns WidgetModel
   */
  static async getWidgetModel(model_id: string) {
    const manager = await JFEM.getWidgetManager(model_id);
    return await manager.get_model(model_id);
  }

  /**
   * Get the WidgetManger searching all known kernels.
   *
   * @param model_id The widget model id
   * @returns
   */
  static async getWidgetManager(
    model_id: string,
    delays = [100, 5000]
  ): Promise<KernelWidgetManager> {
    for (const sleepTime of delays) {
      for (const jfem of Private.jfems.values()) {
        if (jfem.widget_manager.has_model(model_id)) {
          return jfem.widget_manager;
        }
      }
      await new Promise(resolve => setTimeout(resolve, sleepTime));
    }
    throw new Error(
      `Failed to locate the KernelWidgetManager for model_id='${model_id}'`
    );
  }

  /**
   *
   * @param restart Restart the kernel
   */
  static async startIpylabKernel(restart = false) {
    if (restart) {
      const model = await IpylabModel.sessionManager.findByPath('ipylab');
      if (model) {
        await IpylabModel.app.serviceManager.kernels.shutdown(model.kernel.id);
      }
    }
    await IpylabModel.JFEM.getModelByVpath('ipylab');
  }

  /**
   * Open a console using vpath for path.
   *
   * @param args not used.
   * @returns
   */
  static async openConsole(args: any) {
    const currentWidget = JFEM.tracker.currentWidget;
    const ipylabSettings = (currentWidget as any)?.ipylabSettings;
    const jfem = await JFEM.getModelByVpath(ipylabSettings.vpath);
    const payload = { cid: ipylabSettings.cid };
    return await jfem.scheduleOperation('open_console', payload, 'auto');
  }

  /**
   * Opening/close the console using vpath.
   *
   * logconsole:open corresponds to a toggle command, so we the best
   * we can do is toggle the console.
   *
   * @param args not used.
   */
  static async toggleLogConsole(args: any) {
    const currentWidget = JFEM.tracker.currentWidget;
    const ipylabSettings = (currentWidget as any)?.ipylabSettings;
    const source = ipylabSettings.vpath;
    JFEM.app.commands.execute('logconsole:open', { source });
  }

  logger: ILogger;
  static loggerRegistry: ILoggerRegistry;
}

IpylabModel.JFEM = JupyterFrontEndModel;
const JFEM = JupyterFrontEndModel;

/**
 * A namespace for private data
 */
namespace Private {
  /**
   * Mapping of vpath to JupyterFrontEndModel
   */
  export const vpathTojfem = new Map<
    string,
    PromiseDelegate<JupyterFrontEndModel>
  >();

  /**
   * Mapping of kernelId to JupyterFrontEndModel
   */
  export const jfems = new Map<string, JupyterFrontEndModel>();
}
