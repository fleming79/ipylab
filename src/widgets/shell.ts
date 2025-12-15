// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { MainAreaWidget } from '@jupyterlab/apputils';
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
   * Add a widget to the application shell.
   *
   * This function can handle ipywidgets and native Widgets and  be used to
   * move widgets about the shell.
   *
   * Generative widget creation is supported with 'evaluate' using the same
   * code as 'evalute'. The evaluated code MUST return a widget with a view
   * to be valid.
   *
   * @param args An object with area, options, connection_id, id, vpath & evaluate.
   */

  private static async addToShell(args: any): Promise<Widget> {
    let widget: Widget | MainAreaWidget;

    try {
      widget = await ShellModel.toLuminoWidget(args);
      // Create a new lumino widget
    } catch (e) {
      if (args.evaluate) {
        // Evaluate code in python to get a panel and then add it to the shell.
        const jfem = await ShellModel.JFEM.getModelByVpath(
          args.vpath,
          args.preferredKernel
        );
        return await jfem.scheduleOperation('shell_eval', args, 'object');
      } else {
        throw e;
      }
    }
    args.connection_id =
      args.connection_id ||
      ShellModel.ConnectionModel.new_id('ShellConnection');
    if (args.asMainArea && !(widget instanceof MainAreaWidget)) {
      widget.addClass('ipylab-MainArea');
      const w = (widget = new MainAreaWidget({ content: widget }));
      w.toolbar.dispose();
      w.contentHeader.dispose();
      w.id = args.connection_id;
    }
    ShellModel.ConnectionModel.registerConnection(args.connection_id, widget);

    widget.id = widget.id || args.connection_id || UUID.uuid4();

    const currentWidget = ShellModel.app.shell?.currentWidget;
    ShellModel.app.shell.add(widget as any, args.area || 'main', args.options);

    // Close the launcher
    if (currentWidget?.id?.startsWith('launcher')) {
      currentWidget?.dispose();
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
