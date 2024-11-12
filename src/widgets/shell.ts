// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.
import { MainAreaWidget } from '@jupyterlab/apputils';
import { DocumentWidget } from '@jupyterlab/docregistry';
import { UUID } from '@lumino/coreutils';
import { Widget } from '@lumino/widgets';
import { IpylabModel } from './ipylab';
import { ILabShell } from '@jupyterlab/application';

const AREAS: Array<ILabShell.Area> = [
  'main',
  'left',
  'right',
  'header',
  'top',
  'menu',
  'bottom'
];

export class ShellModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return { ...super.defaults(), _model_name: 'ShellModel' };
  }

  setReady(): void {
    this.base.currentChanged.connect(this._currentChanged, this);
    super.setReady();
  }

  _currentChanged() {
    const id = this.base.currentWidget?.id;
    if (id && id !== this.get('current_widget_id')) {
      this.set('current_widget_id', id);
      this.save_changes();
    }
  }

  close(comm_closed?: boolean): Promise<void> {
    this.base.currentChanged.disconnect(this._currentChanged, this);
    return super.close(comm_closed);
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'addToShell':
        return await ShellModel.addToShell(payload.args);
      case 'getWidget':
        if (!payload.id) {
          return this.base.currentWidget;
        }
        return ShellModel.getLuminoWidgetFromShell(payload.id);
      case 'getWidgetIds':
        return ShellModel.listWidgetIds();
      default:
        return await super.operation(op, payload);
    }
  }

  /**
   * Provided for IpylabModel.tracker for restoring widgets to the shell.
   * @param args `ipylabSettings` in 'addToShell'
   */
  static async restoreToShell(args: any) {
    const sessions = ShellModel.app.serviceManager.sessions;
    if (!args.evaluate && !(await sessions.findByPath(args.vpath))) {
      // Don't create a kernel if a model doesn't exist.
      return;
    }

    await ShellModel.JFEM.getModelByVpath(args.vpath);
    await new Promise(resolve => {
      setTimeout(resolve, 10000);
      ShellModel.addToShell(args).then(resolve, e => {
        resolve(null);
        if (args.evaluate) {
          throw e;
        }
      });
    });
  }

  /**
   * Add a widget to the application shell.
   *
   * This function can handle ipywidgets and native Widgets and  be used to
   * move widgets about the shell.
   *
   * Ipywidgets are added to a tracker enabling restoration from a running
   * kernel such as page refreshing and switching workspaces.
   *
   * Generative widget creation is supported with 'evaluate' using the same
   * code as 'evalute'. The evaluated code MUST return a widget with a view
   * to be valid.
   *
   * @param args An object with area, options, cid, id, vpath & evaluate.
   */

  private static async addToShell(args: any): Promise<Widget> {
    let widget: Widget | MainAreaWidget;

    try {
      widget = await ShellModel.toLuminoWidget(args);
      // Create a new lumino widget
    } catch (e) {
      if (args.evaluate) {
        // Evaluate code in python to get a panel and then add it to the shell.
        const jfem = await ShellModel.JFEM.getModelByVpath(args.vpath);
        return await jfem.scheduleOperation('shell_eval', args, 'object');
      } else {
        throw e;
      }
    }
    args.cid =
      args.cid || ShellModel.ConnectionModel.new_cid('ShellConnection');
    if (args.asDocument && !(widget instanceof DocumentWidget)) {
      widget.addClass('ipylab-Document');
      const jfem = await ShellModel.JFEM.getModelByVpath(args.vpath);
      const context = jfem.context as any;
      const label = widget?.title?.label || args.vpath;
      const w = (widget = new DocumentWidget({ context, content: widget }));
      w.node.removeChild(w.toolbar.node);
      w.id = args.cid;
      // Disconnect the following callback which overwrites the `title.label`.
      w.title.changed.disconnect((w as any)._onTitleChanged, w);
      w.title.label = label;
      w.title.caption = w.title.caption || `vpath=${args.vpath}`;
    }
    ShellModel.ConnectionModel.registerConnection(args.cid, widget);

    widget.id = widget.id || args.cid || UUID.uuid4();
    ShellModel.app.shell.add(widget as any, args.area || 'main', args.options);

    // Register widgets originating from IpyWidgets
    if (args.ipy_model) {
      if (!ShellModel.tracker.has(widget)) {
        (widget as any).ipylabSettings = args;
        ShellModel.tracker.add(widget);
      } else {
        (widget as any).ipylabSettings.area = args.area;
        (widget as any).ipylabSettings.options = args.options;
        ShellModel.tracker.save(widget);
      }
    }
    return widget;
  }

  /**
   * Get the lumino widget from the shell using its id.
   *
   * @param id
   */
  static getLuminoWidgetFromShell(id: string): Widget | null {
    for (const area of AREAS) {
      for (const widget of ShellModel.labShell.widgets(area)) {
        if (widget.id === id) {
          return widget;
        }
      }
    }
  }

  /**
   * Get mapping of area to array widget ids for all areas.
   */
  static listWidgetIds(): any {
    const data = Object.create(null);
    for (const area of AREAS) {
      const items: Array<string> = [];
      data[area] = items;
      for (const widget of ShellModel.labShell.widgets(area)) {
        items.push(widget.id);
      }
    }
    return data;
  }
  readonly base: ILabShell;
}

IpylabModel.ShellModel = ShellModel;
