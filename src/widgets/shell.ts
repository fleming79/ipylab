// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { MainAreaWidget } from '@jupyterlab/apputils';
import { UUID } from '@lumino/coreutils';
import { IpylabModel } from './ipylab';
import { Widget } from '@lumino/widgets';

export class ShellModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ShellModel' };
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'addToShell':
        return await ShellModel.addToShell(payload.args);
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
    await ShellModel.JFEM.getModelByVpath(args.vpath);
    try {
      await ShellModel.addToShell(args);
    } catch (e) {
      if (args.evaluate) {
        throw e;
      }
    }
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

  private static async addToShell(args: any): Promise<Widget> {
    let widget: Widget | MainAreaWidget;

    try {
      widget = await IpylabModel.toLuminoWidget(args);
      // Create a new lumino widget
    } catch (e) {
      if (args.evaluate) {
        // Evaluate code in python to get a panel and then add it to the shell.
        const jfem = await IpylabModel.JFEM.getModelByVpath(args.vpath);
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
    args.cid =
      args.cid || IpylabModel.ConnectionModel.new_cid('ShellConnection');
    IpylabModel.ConnectionModel.registerConnection(args.cid, widget);

    widget.id = widget.id || args.cid || UUID.uuid4();
    IpylabModel.app.shell.add(widget as any, args.area || 'main', args.options);

    // Register widgets originating from IpyWidgets
    if (args.ipy_model) {
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
}
