// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import {
  ICallbacks,
  ISerializers,
  IWidgetRegistryData,
  WidgetModel
} from '@jupyter-widgets/base';
import { KernelWidgetManager } from '@jupyter-widgets/jupyterlab-manager';
import { ILabShell, JupyterFrontEnd, LabShell } from '@jupyterlab/application';
import {
  ICommandPalette,
  Notification,
  SessionContext,
  SessionContextDialogs,
  WidgetTracker
} from '@jupyterlab/apputils';
import { IDefaultFileBrowser } from '@jupyterlab/filebrowser';
import { ILauncher } from '@jupyterlab/launcher';
import { IMainMenu, MainMenu } from '@jupyterlab/mainmenu';
import { ObservableMap } from '@jupyterlab/observables';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import type { Kernel, Session } from '@jupyterlab/services';
import { ITranslator } from '@jupyterlab/translation';
import { CommandRegistry } from '@lumino/commands';
import {
  JSONObject,
  JSONValue,
  PromiseDelegate,
  UUID
} from '@lumino/coreutils';
import { IDisposable, IObservableDisposable } from '@lumino/disposable';
import { Signal } from '@lumino/signaling';
import { Widget } from '@lumino/widgets';
import { MODULE_NAME, MODULE_VERSION } from '../version';
import type { ConnectionModel } from './connection';
import type { JupyterFrontEndModel } from './frontend';
import {
  executeMethod,
  getNestedProperty,
  listProperties,
  setNestedProperty,
  toFunction,
  toJSONsubstituteCylic,
  updateProperty
} from './utils';
export {
  CommandRegistry,
  IDisposable,
  ILabShell,
  ILauncher,
  IObservableDisposable,
  ISerializers,
  ITranslator,
  JSONObject,
  JSONValue,
  JupyterFrontEnd,
  Widget
};

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
      _model_module: IpylabModel.model_module,
      _model_module_version: IpylabModel.model_module_version,
      _view_name: null,
      _view_module: IpylabModel.view_module,
      _view_module_version: IpylabModel.view_module_version
    };
  }

  initialize(attributes: any, options: any): void {
    super.initialize(attributes, options);
    this.set('ready', false);
    this.save_changes();
    this.on('msg:custom', this.onCustomMessage, this);
    IpylabModel.onKernelLost(this.kernel, this.close, this);
    this.widget_manager.get_model(this.model_id).then(() => this.ipylabInit());
  }

  /**
   * Finish initializing the model.
   * Overload this method as required.
   *
   * When overloading nsuring to call:
   *  `await super.ipylabInit()`
   *
   * @param base The base of the model with regard to all methods that use base.
   */
  async ipylabInit(base: any = null) {
    if (!base) {
      let subpath;
      [base, subpath] = this.toBaseAndSubpath(this.get('ipylab_base'), 'this');
      base = getNestedProperty({ obj: base, subpath, nullIfMissing: true });
      if (!base) {
        this.close();
        this.error(`Invalid ipylab_base '${this.get('ipylab_base')}'!`);
      }
    }
    Object.defineProperty(this, 'base', {
      value: base,
      writable: false,
      configurable: true
    });
    this.set_ready();
  }

  set_ready() {
    this.set('ready', true);
    this.save_changes();
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

  error(msg: string): never {
    throw new Error(`${msg}\nPython class = ${this.get('_python_class')}`);
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
   * Perform a generic operation locating the  and return the result.
   *
   * @param op Name of the operation.
   * @param kwgs Options relevant to the operation.
   * @returns Raw result of the operation.
   */
  async genericOperation(payload: any): Promise<any> {
    payload.obj = this.getBase(payload.basename);
    switch (payload.genericOperation) {
      case 'executeMethod':
        return await executeMethod(payload);
      case 'getProperty':
        return await getNestedProperty(payload);
      case 'listProperties':
        return listProperties(payload);
      case 'setProperty':
        return setNestedProperty(payload);
      case 'updateProperty':
        return updateProperty(payload);
      default:
        this.error(`'${payload.methodName}' has not been implemented`);
    }
  }

  /**
   * Handle messages
   * There are two types:
   * 1. Response to requested operation sent to Python (ipylab_FE).
   * 2. Operation requests received from the Python (ipylab_PY).
   *
   * Both types specify ipylab_## = uuid (unique identifier)
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
      this.do_operation_for_python(content);
    } else if (content.close) {
      this.close(true);
    }
  }

  /**
   * Perform an operation request from Python.
   * @param content
   */
  private async do_operation_for_python(content: any) {
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
   * Replace parts in obj that are indicated by the arrays.
   *
   * @param obj The object (map) with elements to be replaced.
   * @param toLuminoWidget A list of elements to replace with widgets.
   * @param toObject A list of elements to replace with objects.
   */
  async replaceParts(
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
   * @returns [base, subpath]
   */
  private toBaseAndSubpath(
    value: string | Array<string>,
    default_basename = 'base'
  ): [any, string] {
    let basename = default_basename;
    if (value instanceof Array) {
      [basename, value] = value;
    }
    return [this.getBase(basename), value ?? ''];
  }

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
        this.error(`Invalid basename: "${basename}"`);
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
        if (obj) {
          try {
            return await IpylabModel.toObject(null, obj);
          } catch {
            /* empty */
          }
        }
        return obj;
      default:
        this.error(`Invalid return mode: '${transform}'`);
    }
  }

  /**
   * Start a new session context and possibly a new kernel.
   *
   * @returns
   */
  static async newSessionContext(vpath: string): Promise<SessionContext> {
    if (!vpath) {
      throw new Error('vpath not provided');
    }
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
    const kernel = sessionContext.session.kernel;
    await IpylabModel.ensureFrontend(kernel, vpath);
    return sessionContext;
  }

  /**
   * Get the WidgetManger searching all known kernels.
   *
   * @param model_id The widget model id
   * @returns
   */
  static async getWidgetManager(
    model_id: string
  ): Promise<KernelWidgetManager> {
    return await (KernelWidgetManager as any).getManager(model_id, [100, 5000]);
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
    const manager = await IpylabModel.getWidgetManager(model_id);
    return await manager.get_model(model_id);
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
      let model = await IpylabModel.getWidgetModel(ipy_model);
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
   * Get the lumino widget from the shell using its id.
   *
   * @param id
   * @returns
   */
  static getLuminoWidgetFromShell(id: string): Widget | null {
    for (const area of [
      'main',
      'header',
      'top',
      'menu',
      'left',
      'right',
      'bottom'
    ]) {
      for (const widget of IpylabModel.labShell.widgets(
        area as ILabShell.Area
      )) {
        if (widget.id === id) {
          return widget;
        }
      }
    }
  }

  /**
   * Ensure the JupyterFrontendModel 'app' is running in the kernel.
   * @param kernel
   */
  static async ensureFrontend(kernel: Kernel.IKernelConnection, vpath = '') {
    if (!IpylabModel.jfemPromises.has(kernel.id)) {
      const manager = new KernelWidgetManager(kernel, IpylabModel.rendermime);
      IpylabModel.jfemPromises.set(kernel.id, new PromiseDelegate());
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
    return await IpylabModel.jfemPromises.get(kernel.id).promise;
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
        obj = await IpylabModel.getWidgetModel(model_id);
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
   * Call slot when kernel is restarting or dead.
   *
   * As soon as the kernel is restarted, all Python objects are lost. Use this
   * function to close the corresponding frontend objects.
   * @param kernel
   * @param slot
   * @param thisArg
   * @param onceOnly -  [true] Once called the slot will be disconnected.
   */
  static onKernelLost(
    kernel: Kernel.IKernelConnection,
    slot: any,
    thisArg?: any,
    onceOnly = true
  ) {
    const id = kernel.id;
    if (!Private.kernelLostSlot.has(id)) {
      kernel.statusChanged.connect(_onKernelStatusChanged);
      Private.kernelLostSlot.set(id, new Signal<any, null>(kernel));
      kernel.disposed.connect(() => {
        Private.kernelLostSlot.get(id).emit(null);
        Signal.clearData(Private.kernelLostSlot.get(id));
        Private.kernelLostSlot.delete(id);
        kernel.statusChanged.disconnect(_onKernelStatusChanged);
      });
    }
    const callback = () => {
      slot.bind(thisArg)();
      if (onceOnly) {
        Private.kernelLostSlot.get(id)?.disconnect(callback);
      }
    };
    Private.kernelLostSlot.get(id).connect(callback);
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
   * Promises to frontends that may be loading.
   */
  static jfemPromises = new Map<
    string,
    PromiseDelegate<JupyterFrontEndModel>
  >();
  static get sessionManager(): Session.IManager {
    return IpylabModel.app.serviceManager.sessions;
  }

  static serializers: ISerializers = {
    ...WidgetModel.serializers
  };
  widget_manager: KernelWidgetManager;
  private _pendingOperations = new Map<string, PromiseDelegate<any>>();
  readonly base: any;
  static model_name: string = 'IpylabModel';
  static model_module = MODULE_NAME;
  static model_module_version = MODULE_VERSION;
  static view_module: string;
  static view_module_version = MODULE_VERSION;
  static initial_load: boolean;
  static ipylabKernelReady = new PromiseDelegate<boolean>();
  static app: JupyterFrontEnd;
  static rendermime: IRenderMimeRegistry;
  static labShell: LabShell;
  static defaultBrowser: IDefaultFileBrowser;
  static palette: ICommandPalette;
  static translator: ITranslator;
  translator = IpylabModel.translator.load('jupyterlab');
  static launcher: ILauncher;
  static mainMenu: IMainMenu;
  static exports: IWidgetRegistryData;
  static tracker = new WidgetTracker<Widget>({ namespace: 'ipylab' });
  static JFEM: typeof JupyterFrontEndModel;
  static ConnectionModel: typeof ConnectionModel;
  static Notification = Notification;
}

/**
 * React to changes to the kernel status.
 */
function _onKernelStatusChanged(kernel: Kernel.IKernelConnection) {
  if (['dead', 'restarting'].includes(kernel.status)) {
    Private.kernelLostSlot.get(kernel.id).emit(null);
  }
}

/**
 * A namespace for private data
 */
namespace Private {
  export const kernelLostSlot = new ObservableMap<
    Signal<Kernel.IKernelConnection, null>
  >();
}
