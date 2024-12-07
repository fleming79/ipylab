// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { CommandRegistry } from '@lumino/commands';
import { IpylabModel } from './ipylab';
import { IDisposable } from '@lumino/disposable';
import { ObservableDisposable } from '../observable_disposable';

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

  setReady() {
    this.base.commandChanged.connect(this.sendCommandList, this);
    this.sendCommandList();
    super.setReady();
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
    const mappings = {
      caption: () => options.caption ?? '',
      className: () => options.className ?? '',
      dataset: () => options.dataset ?? {},
      describedBy: () => options.describedBy ?? '',
      execute: async (args: any) => {
        const w1 = IpylabModel.app.shell.currentWidget;
        const cid = w1 ? IpylabModel.ConnectionModel.get_cid(w1, true) : '';
        const payload = { id, args, cid };
        return await this.scheduleOperation('execute', payload, 'object');
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
    const command = this.base.addCommand(id, mappings as any);
    return new CommandLink(command, id, options, mappings);
  }
  public readonly base: CommandRegistry;
}

class CommandLink extends ObservableDisposable {
  constructor(
    command: IDisposable,
    id: string = '',
    options: CommandRegistry.ICommandOptions,
    mappings: any
  ) {
    super();
    this.command = command;
    this.id = id;
    this.config = options;
    this.mappings = mappings;
  }

  dispose(): void {
    if (this.isDisposed) {
      return;
    }
    this.command.dispose();
    super.dispose();
  }
  readonly id: string;
  readonly config: CommandRegistry.ICommandOptions;
  readonly command: IDisposable;
  readonly mappings: any;
}
