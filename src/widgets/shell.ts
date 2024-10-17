// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { MainAreaWidget } from '@jupyterlab/apputils';
import { JupyterFrontEndModel } from './frontend';
import { IpylabModel, Widget } from './ipylab';

export class ShellModel extends IpylabModel {
  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'addToShell':
        return await ShellModel.addToShell(payload);
      default:
        return await super.operation(op, payload);
    }
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
    await ShellModel.addToShell(args);
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
   * code as 'evalute'. The evaluated code MUST return a widget with a view to be valid.
   *
   * @param args An object with area, options, cid, id, vpath & evaluate.
   */

  static async addToShell(args: any): Promise<Widget> {
    let widget: Widget | MainAreaWidget;
    let vpath: string;

    if (!args.cid) {
      throw new Error('cid not provided!');
    }

    try {
      const info = await IpylabModel.toLuminoWidget(args);

      ({ widget, vpath } = info);
      // Create a new lumino widget
    } catch (e) {
      if (args.evaluate) {
        // Evaluate code in python to get a panel and then add it to the shell.
        const jfem = await JupyterFrontEndModel.getModel(args.vpath);
        return await jfem.scheduleOperation('shell_eval', args, 'object');
      } else {
        throw e;
      }
    }
    if (
      (args.area === 'main' && !(widget instanceof MainAreaWidget)) ||
      typeof widget.title === 'undefined'
    ) {
      // Wrap the widget with a MainAreaWidget
      const w = (widget = new MainAreaWidget({ content: widget }));
      w.node.removeChild(w.toolbar.node);
      w.addClass('ipylab-MainArea');
    }

    widget.id = widget.id || args.cid;
    IpylabModel.registerConnection(args.cid, widget);
    IpylabModel.app.shell.add(widget as any, args.area || 'main', args.options);

    // Register widgets originating from IpyWidgets or evaluate
    if (args.ipy_model) {
      // The property `isIpyWidget`is added in `toLuminoWidget`
      args.vpath = vpath;
      widget.addClass('ipylab-shell');
      if (!IpylabModel.tracker.has(widget)) {
        (widget as any).ipylabSettings = args;
        IpylabModel.tracker.add(widget);
      } else {
        (widget as any).ipylabSettings.area = args.area;
        (widget as any).ipylabSettings.options = args.options;
        IpylabModel.tracker.save(widget);
      }
    }
    return widget;
  }

  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ShellModel' };
  }
}
