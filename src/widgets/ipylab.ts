// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { DOMWidgetModel, ICallbacks } from '@jupyter-widgets/base';
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
import type { JupyterFrontEndModel } from './frontend';
import type { ShellModel } from './shell';
import { IEditorServices } from '@jupyterlab/codeeditor';

/**
 * Base model for Ipylab.
 *
 * Subclass as required but can also be used directly.
 */
export class IpylabModel extends DOMWidgetModel {
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
        this.ipylabSend({
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
      this.ipylabSend({ closed: true });
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
  ipylabSend(
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
    this.send({ ipylab: content }, callbacks, buffers);
  }

  /**
   * Sends a signal to the Python backend.
   *
   * @param args - The arguments to send with the signal. Must be a JSON-serializable value.
   */
  sendSignal(args: JSONValue) {
    this.ipylabSend({ signal: args });
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
    this.ipylabSend({ ipylab_FE, operation, payload });
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
   * Handles custom messages received from the Python backend.
   *
   * @param msg The message received from the backend.
   */
  protected onCustomMessage(msg: any) {
    if (msg.ipylab) {
      this._onBackendMessage(JSON.parse(msg.ipylab));
    }
  }

  /**
   * Handles messages received from the backend.
   *
   * This method processes messages from the Python backend, which can include:
   * - Results of operations requested by the frontend.
   * - Requests for operations to be performed by the frontend on behalf of the backend.
   * - Instructions to close the widget.
   *
   * @param content - The content of the message received from the backend.  The content
   *                  is expected to have one of the following properties: `ipylab_FE`, `ipylab_PY`, or `close`.
   *
   * If `content.ipylab_FE` is present:
   *   - Retrieves the corresponding pending operation.
   *   - Replaces parts of the widget based on the received keyword arguments and conversion flags.
   *   - Resolves or rejects the pending operation based on the success of the `replaceParts` method and the presence of an error in the content.
   *
   * If `content.ipylab_PY` is present:
   *   - Executes an operation requested by the Python backend using the `doOperationForPython` method.
   *
   * If `content.close` is present:
   *   - Closes the widget.
   */
  private async _onBackendMessage(content: any) {
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
    }
  }

  /**
   * Executes a specified operation in Python, handles data transformation,
   * and sends the result back to the Python environment.
   *
   * @param content - An object containing the operation details,
   * including the operation name, Python object identifier,
   * transformation instructions, keyword arguments, and flags for
   * Lumino widget and object conversion.
   *
   * @remarks
   * This method orchestrates the execution of a Python operation,
   * potentially transforming the result before sending it back.
   * It also handles error reporting to the Python environment.
   *
   * The `content` object is expected to have the following properties:
   * - `operation`: The name of the operation to execute in Python.
   * - `ipylab_PY`: An identifier for the Python object associated with the operation.
   * - `transform`: Instructions for transforming the result object.
   * - `kwgs`: Keyword arguments to pass to the Python operation.
   * - `toLuminoWidget`: A flag indicating whether to convert objects to Lumino widgets.
   * - `toObject`: A flag indicating whether to convert objects to plain JavaScript objects.
   *
   * The method performs the following steps:
   * 1. Replaces parts of the keyword arguments based on `toLuminoWidget` and `toObject` flags.
   * 2. Executes the specified operation with the provided keyword arguments.
   * 3. Extracts the payload and buffers from the result object, if present.
   * 4. Transforms the result object using the provided transformation instructions.
   * 5. Sends the transformed payload back to the Python environment.
   * 6. If an error occurs during any of these steps, it sends an error message
   *    back to the Python environment and logs the error to the console.
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
      this.ipylabSend({ ipylab_PY, operation, payload }, null, buffers);
    } catch (e) {
      this.ipylabSend({
        operation,
        ipylab_PY,
        error: `${(e as Error).message}`
      });
      console.error(e);
    }
  }

  /**
   * Replaces parts of a nested object with Lumino widgets or plain JavaScript objects.
   *
   * @param obj The object whose parts need to be replaced.
   * @param toLuminoWidget An array of subpaths within the object that should be replaced with Lumino widgets. Each subpath is a string representing the path to the property (e.g., 'a.b.c').
   * @param toObject An array of subpaths within the object that should be replaced with plain JavaScript objects.  Each subpath is a string representing the path to the property (e.g., 'a.b.c').
   *
   * @remarks
   * The `toLuminoWidget` replacements are performed first.
   * The `getNestedProperty` function is used to retrieve the value at the given subpath.
   * The `IpylabModel.toLuminoWidget` method is used to convert the value to a Lumino widget.
   * The `setNestedProperty` function is used to set the new widget value at the given subpath.
   *
   * For `toObject` replacements, the `toBaseAndSubpath` method is used to split the value into a base and subpath.
   * The `IpylabModel.toObject` method is then used to convert the value to a plain JavaScript object.
   * Finally, the `setNestedProperty` function is used to set the new object value at the given subpath.
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
   * Converts a value, which can be a string or an array, into a base and subpath.
   *
   * If the value is an array, the first element is treated as the basename and the second as the subpath.
   * If the value is a string, it's treated as the subpath, and a default basename is used.
   *
   * @param value The input value, which can be a string or an array of strings.
   * @param defaultBasename The default basename to use if the value is a string. Defaults to 'base'.
   * @returns A tuple containing the base (obtained from `this.getBase` using the basename) and the subpath.
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
   * Transforms an object based on the specified transformation type.
   *
   * @param obj The object to transform.
   * @param args The transformation arguments. If a string, it's treated as the transformation type.
   *             If an object, it should contain a `transform` property specifying the transformation type,
   *             and other properties relevant to the specific transformation.
   * @returns A promise resolving to the transformed object.
   * @throws Error if an invalid transformation type is provided.
   */
  private async transformObject(obj: any, args: string | any): Promise<any> {
    const transform = typeof args === 'string' ? args : args.transform;
    let result, func;

    switch (transform) {
      case 'auto':
        if (obj?.dispose) {
          return { cid: IpylabModel.ConnectionModel.get_cid(obj, true) };
        }
        if (typeof obj?.iterator === 'function') {
          return Array.from(obj);
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
   * Converts a value to an object, handling special cases for strings starting with 'IPY_MODEL_'.
   *
   * If the value is a string, it checks if it starts with 'IPY_MODEL_'. If so, it extracts the model ID and subpath,
   * retrieves the widget model using `IpylabModel.JFEM.getWidgetModel`, and resolves nested properties using `getNestedProperty`.
   * If the value is not a string, it throws an error.
   *
   * @param obj The initial object to traverse, can be a widget model.
   * @param value The value to convert to an object. If it's a string starting with 'IPY_MODEL_', it's treated as a reference to a widget model and a subpath.
   * @param nullIfMissing Optional. If true, returns null if the nested property is missing. Defaults to false.
   * @returns A promise that resolves to the object or nested property.
   * @throws Error if the value is not a string.
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
   * Will call `onKernelLost` when the kernel is dead or restarted.
   * Only required for non PER_KERNEL_WM
   */
  static onKernelLost(
    kernel: IKernelConnection,
    onKernelLost: () => any,
    thisArg: object
  ) {
    if (IpylabModel.PER_KERNEL_WM) {
      // The model and view will now close as needed in ipywidgets.
      return;
    }

    if (!Private.kernelLostCallbacks.has(kernel)) {
      Private.kernelLostCallbacks.set(kernel, new Set());
      kernel.statusChanged.connect(_onKernelStatusChanged);
    }
    Private.kernelLostCallbacks.get(kernel).add([onKernelLost, thisArg]);
  }

  static get sessionManager(): Session.IManager {
    return IpylabModel.app.serviceManager.sessions;
  }

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
  static editorServices: IEditorServices;
  static tracker = new WidgetTracker<Widget>({ namespace: 'ipylab' });
  static JFEM: typeof JupyterFrontEndModel;
  static ConnectionModel: typeof ConnectionModel;
  static ShellModel: typeof ShellModel;
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
