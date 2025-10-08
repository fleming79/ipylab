// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { INotebookTracker } from '@jupyterlab/notebook';
import { ToolbarButton } from '@jupyterlab/apputils';
import { Toolbar } from '@jupyterlab/ui-components';
import { IpylabModel } from './ipylab';

interface IToolbarButtonOptions {
  name: string;
  commandId: string;
  args: any;
  icon: string;
  iconClass: string;
  label?: string;
  tooltip?: string;
  after?: string;
  className?: string;
}

/**
 * The model for a custom toolbar button.
 */
export class CustomToolbarModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): any {
    return {
      ...super.defaults(),
      _model_name: 'CustomToolbarModel'
    };
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'addToolbarButton': {
        return await this.addToolbarButton(payload);
      }
      default:
        return await super.operation(op, payload);
    }
  }

  private async addToolbarButton(
    options: IToolbarButtonOptions
  ): Promise<ToolbarButton> {
    const {
      name,
      commandId,
      args,
      icon,
      iconClass,
      tooltip,
      label,
      after,
      className
    } = options;

    const button = new ToolbarButton({
      icon: icon,
      iconClass: iconClass,
      onClick: () => {
        IpylabModel.app.commands.execute(commandId, args);
      },
      tooltip: tooltip,
      label: label
    });

    if (className) {
      className.split(/\s+/).forEach(button.addClass.bind(button));
    }
    if (this.toolbar.insertAfter(after, name, button)) {
      console.log("button '" + name + "' has been added.");
    }
    return button;
  }

  private get toolbar(): Toolbar {
    return CustomToolbarModel.notebookTracker.currentWidget.toolbar as any;
  }

  static notebookTracker: INotebookTracker;
}
