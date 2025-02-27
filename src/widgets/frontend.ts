// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { KernelWidgetManager } from '@jupyter-widgets/jupyterlab-manager';
import { SessionContext, SessionContextDialogs } from '@jupyterlab/apputils';
import { Kernel } from '@jupyterlab/services';
import { PromiseDelegate } from '@lumino/coreutils';
import { IpylabModel } from './ipylab';

const VPATH = '_vpath';
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
    this.kernelId = this.kernel.id;
    Private.jfems.set(this.kernel.id, this);
  }

  async ipylabInit(base: any = null) {
    const vpath = await JFEM.getVpath(this.kernelId);
    this.set(VPATH, vpath);
    this.set('version', JFEM.app.version);
    this.set('per_kernel_widget_manager_detected', JFEM.PER_KERNEL_WM);
    await super.ipylabInit(base);
    if (!Private.vpathTojfem.has(vpath)) {
      Private.vpathTojfem.set(vpath, new PromiseDelegate());
    }
    Private.vpathTojfem.get(vpath).resolve(this);
  }

  close(comm_closed?: boolean): Promise<void> {
    Private.jfems.delete(this.kernelId);
    Private.vpathTojfem.delete(this.get(VPATH));
    return super.close(comm_closed);
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'evaluate':
        return await JFEM.getModelByVpath(payload.vpath).then(jfem =>
          jfem.scheduleOperation('evaluate', payload, 'object')
        );
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

  /**
   * Get the vpath for given a kernel id.
   */
  static async getVpath(kernelId: string): Promise<string> {
    if (Private.kernelIdToVpath.has(kernelId)) {
      return Private.kernelIdToVpath.get(kernelId);
    }
    for (const session of JFEM.sessionManager.running()) {
      if (session.kernel.id === kernelId) {
        Private.kernelIdToVpath.set(kernelId, session.path);
        return session.path;
      }
    }
    await JFEM.sessionManager.refreshRunning();
    for (const session of JFEM.sessionManager.running()) {
      if (session.kernel.id === kernelId) {
        Private.kernelIdToVpath.set(kernelId, session.path);
        return session.path;
      }
    }
    throw new Error(`Failed to determine vpath for kernelId='${kernelId}'`);
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
      if (!JFEM.PER_KERNEL_WM) {
        throw new Error(
          'A per-kernel KernelWidgetManager is required to start a new session!'
        );
      }
      let kernel: Kernel.IKernelConnection;
      Private.vpathTojfem.set(vpath, new PromiseDelegate());
      await IpylabModel.sessionManager.refreshRunning();
      const model = await IpylabModel.sessionManager.findByPath(vpath);
      if (model) {
        kernel = IpylabModel.app.serviceManager.kernels.connectTo({
          model: model.kernel
        });
      } else {
        const sessionContext = await JFEM.newSessionContext(vpath);
        kernel = sessionContext.session.kernel;
      }
      Private.kernelIdToVpath.set(kernel.id, vpath);
      // Relies on per-kernel widget manager.
      const getManager = (KernelWidgetManager as any).getManager;
      const widget_manager: KernelWidgetManager = await getManager(kernel);
      if (!Private.jfems.has(kernel.id)) {
        widget_manager.kernel.requestExecute({ code: 'import ipylab' }, true);
      }
    }
    return await new Promise((resolve, reject) => {
      const timeoutID = setTimeout(() => {
        const msg = `Failed to get a JupyterFrontendModel for vpath='${vpath}'`;
        Private.vpathTojfem.get(vpath)?.reject(msg);
        Private.vpathTojfem.delete(vpath);
        reject(msg);
      }, 10000);
      Private.vpathTojfem.get(vpath).promise.then(jfem => {
        if (!jfem.commAvailable) {
          jfem.close();
          JupyterFrontEndModel.getModelByVpath(vpath).then(jfem => {
            clearTimeout(timeoutID);
            resolve(jfem);
          });
        } else {
          clearTimeout(timeoutID);
          resolve(jfem);
        }
      });
    });
  }

  /**
   * Create a new session context for vpath.
   *
   * This will automatically starting a new kernel if a session path matching
   * vpath isn't found.
   */
  static async newSessionContext(vpath: string) {
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
    return sessionContext;
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

  kernelId: string;
}

IpylabModel.JFEM = JupyterFrontEndModel;
const JFEM = JupyterFrontEndModel;

/**
 * A namespace for private data
 */
namespace Private {
  /**
   * A mapping of vpath to JupyterFrontEndModel.
   */
  export const vpathTojfem = new Map<
    string,
    PromiseDelegate<JupyterFrontEndModel>
  >();

  /**
   * A mapping of kernelId to vpath, possibly set before the model is created.
   */
  export const kernelIdToVpath = new Map<string, string>();

  /**
   * A mapping of kernelId to JupyterFrontEndModel.
   */
  export const jfems = new Map<string, JupyterFrontEndModel>();
}
