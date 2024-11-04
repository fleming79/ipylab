// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { ICallbacks, ISerializers, WidgetModel } from '@jupyter-widgets/base';
import { KernelWidgetManager } from '@jupyter-widgets/jupyterlab-manager';
import { JupyterFrontEnd, LabShell } from '@jupyterlab/application';
import {
  ICommandPalette,
  Notification,
  WidgetTracker
} from '@jupyterlab/apputils';
import { IDefaultFileBrowser } from '@jupyterlab/filebrowser';
import { ILauncher } from '@jupyterlab/launcher';
import { IMainMenu, MainMenu } from '@jupyterlab/mainmenu';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { Kernel, Session } from '@jupyterlab/services';
import { IKernelConnection } from '@jupyterlab/services/lib/kernel/kernel';
import { ITranslator } from '@jupyterlab/translation';
import { JSONValue, PromiseDelegate, UUID } from '@lumino/coreutils';
import { Widget } from '@lumino/widgets';
import {
  executeMethod,
  getNestedProperty,
  listProperties,
  setNestedProperty,
  toFunction,
  toJSONsubstituteCylic,
  updateProperty
} from '../utils';
import { MODULE_NAME, MODULE_VERSION } from '../version';
import type { ConnectionModel } from './connection';
import { JupyterFrontEndModel } from './frontend';

// Determine if the per kernel widget manager is available

/**
 * Base model for common features
 */
export class IpylabModel extends WidgetModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'IpylabModel',
      _model_module: MODULE_NAME,
      _model_module_version: MODULE_VERSION,
      _view_name: null,
      _view_module: null,
      _view_module_version: MODULE_VERSION
    };
  }

  initialize(attributes: any, options: any): void {
    super.initialize(attributes, options);
    this.set('_ready', false);
    this.save_changes();
    this.on('msg:custom', this.onCustomMessage, this);
    IpylabModel.onKernelLost(this.kernel, this.onKernelLost, this);

    if (this.widget_manager.restoredStatus || !IpylabModel.PER_KERNEL_WM) {
      this._startIpylabInit();
    } else {
      // Defer ipylabInit until widget restoration is finished.
      this.widget_manager.restored.connect(this._startIpylabInit, this);
    }
  }

  _startIpylabInit() {
    this.widget_manager.restored.disconnect(this._startIpylabInit, this);
    this.widget_manager.get_model(this.model_id).then(() => this.ipylabInit());
  }

  /**
   * Finish initializing the model.
   * Overload this method as required.
   *
   * When overloading call:
   *  `await super.ipylabInit()`
   *
   * @param base override the base of the instance.
   */
  async ipylabInit(base: any = null) {
    if (!base) {
      let subpath;
      [base, subpath] = this.toBaseAndSubpath(this.get('ipylab_base'), 'this');
      base = getNestedProperty({ obj: base, subpath, nullIfMissing: true });
      if (!base) {
        this.send({
          error: `Invalid ipylab_base '${this.get('ipylab_base')}'!`
        });
        this.close();
      }
    }
    Object.defineProperty(this, 'base', {
      value: base,
      writable: false,
      configurable: true
    });
    this.setReady();
  }

  /**
   * This is called once the object is ready by ipylabInit.
   * It can be overloaded, but shouldn't be called.
   */
  setReady() {
    this.set('_ready', true);
    this.save_changes();
  }

  onKernelLost() {
    this.close(true);
  }

  close(comm_closed?: boolean): Promise<void> {
    this._pendingOperations.forEach(opDone => opDone.reject('Closed'));
    this._pendingOperations.clear();
    comm_closed = comm_closed || !this.commAvailable;
    if (!comm_closed) {
      this.send({ closed: true });
    }
    Object.defineProperty(this, 'base', { value: null });
    return super.close(true);
  }

  save_changes(callbacks?: object): void {
    if (this.commAvailable) {
      super.save_changes(callbacks);
    }
  }

  /**
   * Send a custom msg over the comm.
   */
  send(
    content: any,
    callbacks?: ICallbacks,
    buffers?: ArrayBuffer[] | ArrayBufferView[]
  ) {
    try {
      content = JSON.stringify(content);
    } catch {
      if (content.transform === 'auto') {
        content.payload = {
          cid: IpylabModel.ConnectionModel.get_cid(content.payload, true)
        };
      }
      content = toJSONsubstituteCylic(content);
    }
    super.send(content, callbacks, buffers);
  }

  /**
   * Schedule an operation to be performed in Python.
   * This is a mirror of `Ipylab.operation` in Python.
   *
   * @param operation The name of the operation to perform in Python.
   * @param payload Payload to send to Python.
   * @param transform The type of transformation to apply on the returned result.
   */
  async scheduleOperation(
    operation: string,
    payload: JSONValue,
    transform: any
  ): Promise<any> {
    const ipylab_FE = UUID.uuid4();
    // Create callbacks to be resolved when a custom message is received
    // with the key `ipylab_FE`.
    const opDone = new PromiseDelegate();
    this._pendingOperations.set(ipylab_FE, opDone);
    this.send({ ipylab_FE, operation, payload });
    const result: any = await opDone.promise;
    return await this.transformObject(result, transform);
  }

  /**
   * Perform an operation and return the result.
   *
   * Overload as required.
   *
   * @param op Name of the operation.
   * @param payload Options relevant to the operation.
   * @returns Raw result of the operation.
   */
  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'genericOperation':
        return await this.genericOperation(payload);
      default:
        // Each failed operation should throw an error if it is un-handled
        throw new Error(`genericOperation "${op}" not implemented!`);
    }
  }

  /**
   * Perform a generic operation and return the result.
   */
  async genericOperation(payload: any): Promise<any> {
    payload.obj = this.getBase(payload.basename);
    switch (payload.genericOperation) {
      case 'executeMethod':
        return await executeMethod(payload);
      case 'getProperty':
        return await getNestedProperty(payload);
      case 'listProperties':
        payload.obj = getNestedProperty(payload);
        return listProperties(payload);
      case 'setProperty':
        return setNestedProperty(payload);
      case 'updateProperty':
        return updateProperty(payload);
      default:
        throw new Error(`'${payload.methodName}' has not been implemented`);
    }
  }

  /**
   * Handle messages
   * 1. Response to requested operation sent to Python (ipylab_FE).
   * 2. Operation requests received from the Python (ipylab_PY).
   * 3. close - close always starts from the frontend unless the kernel is lost.
   * 4. Log messages for the Jupyterlab logger.
   *
   * @param msg
   */
  private async onCustomMessage(msg: any) {
    if (typeof msg !== 'string') {
      return;
    }
    const content = JSON.parse(msg);

    if (content.ipylab_FE) {
      // Result of an operation request sent to Python.
      const op = this._pendingOperations.get(content.ipylab_FE);
      const { kwgs, toLuminoWidget, toObject } = content;
      this._pendingOperations.delete(content.ipylab_FE);
      try {
        await this.replaceParts(kwgs, toLuminoWidget, toObject);
      } catch (e) {
        content.error = e;
      }
      if (op) {
        if (content.error) {
          op.reject(new Error(content.error?.repr ?? content.error));
        } else {
          op.resolve(content.payload);
        }
      }
    } else if (content.ipylab_PY) {
      this.doOperationForPython(content);
    } else if (content.close) {
      this.close(true);
    } else if (content.log) {
      const { log, toLuminoWidget, toObject } = content;
      this.replaceParts(log, toLuminoWidget, toObject);
      IpylabModel.JFEM.getModelByKernelId(this.kernel.id).logger.log(log);
    }
  }

  /**
   * Perform an operation request issued from a Python kernel.
   * @param content
   */
  private async doOperationForPython(content: any) {
    const { operation, ipylab_PY, transform } = content;
    const { kwgs, toLuminoWidget, toObject } = content;
    try {
      await this.replaceParts(kwgs, toLuminoWidget, toObject);
      let obj, buffers;
      obj = await this.operation(operation, kwgs);
      if (obj?.payload) {
        buffers = obj.buffers;
        obj = obj.payload;
      }
      const payload = (await this.transformObject(obj, transform)) ?? null;
      this.send({ ipylab_PY, operation, payload }, null, buffers);
    } catch (e) {
      this.send({ operation, ipylab_PY, error: `${(e as Error).message}` });
      console.error(e);
    }
  }

  /**
   * Replace parts in obj that are indicated by the arrays
   * - toLuminoWidget
   * - toObject
   *
   * @param obj The object (map) with elements to be replaced.
   * @param toLuminoWidget A list of elements to replace with widgets.
   * @param toObject A list of elements to replace with objects.
   */
  private async replaceParts(
    obj: Map<string, any>,
    toLuminoWidget?: Array<string>,
    toObject?: Array<string>
  ) {
    if (toLuminoWidget instanceof Array) {
      // Replace values in kwgs with widgets
      for (const subpath of toLuminoWidget) {
        const value = getNestedProperty({ obj, subpath });
        if (value) {
          const lw = await IpylabModel.toLuminoWidget({ id: value });
          setNestedProperty({ obj, subpath, value: lw });
        }
      }
    }
    if (toObject instanceof Array) {
      for (const subpath of toObject) {
        let base, value;
        value = getNestedProperty({ obj, subpath });
        if (value) {
          [base, value] = this.toBaseAndSubpath(value);
          value = await IpylabModel.toObject(base, value);
          setNestedProperty({ obj, subpath, value });
        }
      }
    }
  }

  /**
   * Get the base and subpath from value.
   *
   * When `default_basename` will be used when `value` is a string.
   *
   * @param value can be either [basename, subpath] or subpath.
   * @param defaultBasename A basename to use when value is just a subpath.
   * @returns [base, subpath]
   */
  private toBaseAndSubpath(
    value: string | Array<string>,
    defaultBasename = 'base'
  ): [any, string] {
    let basename = defaultBasename;
    if (value instanceof Array) {
      [basename, value] = value;
    }
    return [this.getBase(basename), value ?? ''];
  }

  /**
   * Get the object referenced by basename.
   */
  private getBase(basename: string) {
    switch (basename) {
      case 'this':
        return this;
      case 'base':
        return this.base;
      case 'IpylabModel':
        return IpylabModel;
      case 'MainMenu':
        return MainMenu;
      default:
        throw new Error(`Invalid basename: "${basename}"`);
    }
  }

  /**
   * Transform the object for sending.
   * @param base
   * @param args The mode as a string or an object with mode and any other parameters.
   * @returns
   */
  private async transformObject(obj: any, args: string | any): Promise<any> {
    const transform = typeof args === 'string' ? args : args.transform;
    let result, func;

    switch (transform) {
      case 'auto':
        if (obj?.dispose) {
          return { cid: IpylabModel.ConnectionModel.get_cid(obj, true) };
        }
        return await obj;
      case 'null':
        return null;
      case 'connection':
        if (args.cid) {
          IpylabModel.ConnectionModel.registerConnection(args.cid, obj);
        }
        return { cid: IpylabModel.ConnectionModel.get_cid(obj, true) };
      case 'advanced':
        // expects args.mappings = {key:transform}
        result = new Object();
        for (const key of Object.keys(args.mappings)) {
          const base = getNestedProperty({ obj, subpath: key });
          (result as any)[key] = await this.transformObject(
            base,
            args.mappings[key]
          );
        }
        return result as any;
      case 'function':
        func = toFunction(args.code).bind(this);
        if (func.constructor.name === 'AsyncFunction') {
          return await func(obj, args);
        }
        return func(obj);
      case 'object':
        // 'object' is used by the frontend only.
        if (obj) {
          try {
            return await IpylabModel.toObject(null, obj);
          } catch {
            return obj;
          }
        }
        return obj;
      default:
        throw new Error(`Invalid return mode: '${transform}'`);
    }
  }

  get kernel(): Kernel.IKernelConnection {
    return (this.widget_manager as any).kernel;
  }

  get commAvailable(): boolean {
    return (
      !this.kernel?.isDisposed &&
      this.comm &&
      !['dead', 'restarting'].includes(this.kernel?.status)
    );
  }

  /**
   * Get or create a lumino widget.
   *
   * @param args: an object with 'id' and 'vpath'
   * args is updated as the object is located
   * @returns
   */
  static async toLuminoWidget({
    cid = '',
    id = '',
    ipy_model = ''
  }: { cid?: string; id?: string; ipy_model?: string } = {}): Promise<Widget> {
    let widget: Widget;

    widget = IpylabModel.ConnectionModel.getConnection(cid) as Widget;
    if (widget instanceof Widget) {
      return widget;
    }
    if (!ipy_model && id.slice(0, 10) === 'IPY_MODEL_') {
      ipy_model = id.slice(10).split(':', 1)[0];
    }
    if (ipy_model) {
      let model = await IpylabModel.JFEM.getWidgetModel(ipy_model);
      if ((model as ConnectionModel).isConnectionModel) {
        model = (model as ConnectionModel).base;
      }
      if (!model.get('_view_name')) {
        const name = model.get('_model_name');
        throw new Error(`Model '${name}' does not have a view!`);
      }
      const manager = model.widget_manager as KernelWidgetManager;
      widget = (await manager.create_view(model, {})).luminoWidget;
      IpylabModel.onKernelLost(manager.kernel, widget.dispose, widget);
    }
    if (!(widget instanceof Widget)) {
      throw new Error(
        `Unable to create a luminoWidget cid='${cid}' id='${id}' ipy_model='${ipy_model}`
      );
    }
    return widget;
  }

  /**
   * Returns the object for the subpath 'value'.
   * 1. If value starts with IPY_MODEL_ it will ignore the base, instead
   *    unpacking the model and return the object relative to subpath after
   *    the model name. If there is no path after the model id it will be the model.
   * 2. The object as specified by the subpath relate to the base will be returned.
   * 3. An error will be thrown if the value doesn't point an existing attribute.
   *
   * @param obj The object to locate the dotted value.
   * @param value The subpath on the base (except for IPY_MODEL_).
   * @param nullIfMissing Return a null instead of throwing an error if missing.
   */
  static async toObject(
    obj: any,
    value: any,
    nullIfMissing = false
  ): Promise<any> {
    if (typeof value === 'string') {
      let subpath = value;
      if (value.slice(0, 10) === 'IPY_MODEL_') {
        let model_id;
        [model_id, subpath] = value.slice(10).split('.', 2);
        obj = await IpylabModel.JFEM.getWidgetModel(model_id);
        if (obj.isConnectionModel) {
          obj = obj.base;
        }
      }
      subpath = subpath ?? '';
      return await getNestedProperty({ obj, subpath, nullIfMissing });
    }
    throw new Error(`Cannot convert this value to an object: ${value}`);
  }

  /**
   * Will call `dispose` once the kernel dead or restarted or disposed.
   */
  static onKernelLost(
    kernel: IKernelConnection,
    onKernelLost: () => any,
    thisArg: object
  ) {
    if (!Private.kernelLostCallbacks.has(kernel)) {
      Private.kernelLostCallbacks.set(kernel, new Set());
      kernel.disposed.connect(_kernelLost);
      kernel.statusChanged.connect(_onKernelStatusChanged);
    }
    Private.kernelLostCallbacks.get(kernel).add([onKernelLost, thisArg]);
  }

  static get sessionManager(): Session.IManager {
    return IpylabModel.app.serviceManager.sessions;
  }

  static serializers: ISerializers = {
    ...WidgetModel.serializers
  };
  widget_manager: KernelWidgetManager;
  private _pendingOperations = new Map<string, PromiseDelegate<any>>();
  readonly base: any;
  static app: JupyterFrontEnd;
  static rendermime: IRenderMimeRegistry;
  static labShell: LabShell;
  static defaultBrowser: IDefaultFileBrowser;
  static palette: ICommandPalette;
  static translator: ITranslator;
  translator = IpylabModel.translator.load('jupyterlab');
  static launcher: ILauncher;
  static mainMenu: IMainMenu;
  static tracker = new WidgetTracker<Widget>({ namespace: 'ipylab' });
  static JFEM: typeof JupyterFrontEndModel;
  static ConnectionModel: typeof ConnectionModel;
  static Notification = Notification;
  static PER_KERNEL_WM = Boolean((KernelWidgetManager as any)?.getManager);
}

/**
 * React to changes to the kernel status.
 */
function _onKernelStatusChanged(kernel: Kernel.IKernelConnection) {
  if (
    [
      'dead',
      'starting',
      'restarting',
      'autorestarting',
      'terminating'
    ].includes(kernel.status)
  ) {
    _kernelLost(kernel);
  }
}

function _kernelLost(kernel: IKernelConnection) {
  if (!Private.kernelLostCallbacks.has(kernel)) {
    return;
  }
  Private.kernelLostCallbacks.get(kernel)?.forEach(cb => cb[0].bind(cb[1])());
  Private.kernelLostCallbacks.get(kernel)?.clear();
  if (kernel.isDisposed) {
    Private.kernelLostCallbacks.delete(kernel);
    kernel.statusChanged.disconnect(_kernelLost);
    kernel.disposed.disconnect(_kernelLost);
  }
}

/**
 * A namespace for private data
 */
namespace Private {
  export const kernelLostCallbacks = new Map<
    IKernelConnection,
    Set<[() => any, object]>
  >();
}
