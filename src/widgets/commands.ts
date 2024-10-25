// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { CommandRegistry } from '@lumino/commands';
import { IDisposable, IpylabModel } from './ipylab';

/**
 * The model for a command registry.
 */
export class CommandRegistryModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'CommandRegistryModel'
    };
  }
  async ipylabInit(base: any = null) {
    if (!base) {
      base =
        this.get('name') === 'Jupyterlab'
          ? IpylabModel.app.commands
          : new CommandRegistry();
    }
    await super.ipylabInit(base);
  }

  set_ready() {
    this.base.commandChanged.connect(this.sendCommandList, this);
    this.sendCommandList();
    super.set_ready();
  }

  /**
   * Close model
   *
   * @param comm_closed - true if the comm is already being closed. If false, the comm will be closed.
   *
   * @returns - a promise that is fulfilled when all the associated views have been removed.
   */
  close(comm_closed = false): Promise<void> {
    this?.base?.commandChanged?.disconnect(this.sendCommandList, this);
    return super.close(comm_closed);
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'execute':
        return await this.base.execute(payload.id, payload.args);
      case 'addCommand':
        return await this.addCommand(payload);
      default:
        return await super.operation(op, payload);
    }
  }

  /**
   * Send the list of commands to the backend.
   */
  private sendCommandList(sender?: object, args?: any): void {
    if (args && args.type !== 'added' && args.type !== 'removed') {
      return;
    }
    this.set('all_commands', this.base.listCommands());
    this.save_changes();
  }

  /**
   * Add a new command to the command registry.
   *
   * @param payload The command options.
   */
  private async addCommand(
    options: CommandRegistry.ICommandOptions & { id: string }
  ): Promise<IDisposable> {
    const { id, isToggleable, icon } = options;

    // Make a new object and define functions so we can dynamically update.
    delete options.icon;
    const isToggled = isToggleable ? () => options.isToggled ?? true : null;
    const options_ = {
      caption: () => options.caption ?? '',
      className: () => options.className ?? '',
      dataset: () => options.dataset ?? {},
      describedBy: () => options.describedBy ?? '',
      execute: async (args: any) => {
        return await this.scheduleOperation('execute', { id, args }, 'object');
      },
      icon: icon,
      iconClass: () => options.iconClass ?? '',
      iconLabel: () => options.iconLabel ?? '',
      isEnabled: () => options.isEnabled ?? true,
      isToggleable,
      isToggled,
      isVisible: () => options.isVisible ?? true,
      label: () => options.label,
      mnemonic: () => Number(options.mnemonic ?? -1),
      usage: () => options.usage ?? ''
    };
    const command = this.base.addCommand(id, options_ as any);
    (command as any).id = id;
    (command as any).config = options;
    return command;
  }
  public readonly base: CommandRegistry;
}
