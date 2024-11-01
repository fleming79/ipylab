// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { IJupyterWidgetRegistry } from '@jupyter-widgets/base';
import {
  ILabShell,
  ILayoutRestorer,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette } from '@jupyterlab/apputils';
import { IDefaultFileBrowser } from '@jupyterlab/filebrowser';
import { ILauncher } from '@jupyterlab/launcher';
import { ILoggerRegistry } from '@jupyterlab/logconsole';
import { IMainMenu } from '@jupyterlab/mainmenu';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { ISettingRegistry } from '@jupyterlab/settingregistry';
import { ITranslator } from '@jupyterlab/translation';
import { MODULE_NAME, MODULE_VERSION } from './version';
import { IpylabModel, JupyterFrontEndModel, ShellModel } from './widget';
import { PER_KERNEL_WM } from './widgets/frontend';

const PLUGIN_ID = 'ipylab:settings';

/**
 * The command IDs used by the plugin.
 */
namespace CommandIDs {
  export const restore = 'ipylab:restore';
  export const checkStartKernel = 'ipylab:check-start-kernel';
  export const openConsole = 'ipylab:open-console';
  export const toggleLogConsole = 'ipylab:toggle-log-console';
}

/**
 * The default plugin.
 */
const extension: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  autoStart: true,
  requires: [IJupyterWidgetRegistry, IRenderMimeRegistry, ISettingRegistry],
  optional: [
    ILayoutRestorer,
    ICommandPalette,
    ILabShell,
    IDefaultFileBrowser,
    ILauncher,
    ITranslator,
    IMainMenu,
    ILoggerRegistry
  ],
  activate: activate
};

/**
 * Activate the JupyterLab extension.
 *
 * @param app Jupyter Front End
 * @param registry Jupyter Widget Registry
 * @param palette Jupyter Commands
 * @param labShell Jupyter Shell
 * @param defaultBrowser Jupyter Default File Browser
 * @param launcher [optional] Jupyter Launcher
 * @param translator Jupyter Translator
 */
async function activate(
  app: JupyterFrontEnd,
  registry: IJupyterWidgetRegistry,
  rendermime: IRenderMimeRegistry,
  settings: ISettingRegistry,
  restorer: ILayoutRestorer,
  palette: ICommandPalette,
  labShell: ILabShell | null,
  defaultBrowser: IDefaultFileBrowser | null,
  launcher: ILauncher | null,
  translator: ITranslator | null,
  mainMenu: IMainMenu | null,
  loggerRegistry: ILoggerRegistry | null
): Promise<void> {
  // add globals
  IpylabModel.app = app;
  IpylabModel.rendermime = rendermime;
  IpylabModel.labShell = labShell;
  IpylabModel.defaultBrowser = defaultBrowser;
  IpylabModel.palette = palette;
  IpylabModel.translator = translator;
  IpylabModel.launcher = launcher;
  IpylabModel.mainMenu = mainMenu;
  IpylabModel.JFEM.loggerRegistry = loggerRegistry;

  const exports = {
    name: MODULE_NAME,
    version: MODULE_VERSION,
    exports: await import('./widget')
  };

  registry.registerWidget(exports);

  app.commands.addCommand(CommandIDs.openConsole, {
    execute: JupyterFrontEndModel.openConsole,
    label: 'Open console'
  });
  app.commands.addCommand(CommandIDs.toggleLogConsole, {
    execute: JupyterFrontEndModel.toggleLogConsole,
    label: 'Toggle log console'
  });
  app.contextMenu.addItem({
    command: CommandIDs.openConsole,
    selector: '.ipylab-shell',
    rank: 1
  });
  app.contextMenu.addItem({
    command: CommandIDs.toggleLogConsole,
    selector: '.ipylab-shell',
    rank: 2
  });

  let when;
  if (PER_KERNEL_WM) {
    app.commands.addCommand(CommandIDs.restore, {
      execute: ShellModel.restoreToShell
    });
    app.commands.addCommand(CommandIDs.checkStartKernel, {
      label: 'Start or restart ipylab kernel',
      caption: 'Start or restart  the python kernel with path="ipylab".',
      execute: () => IpylabModel.JFEM.startIpylabKernel(true)
    });

    palette.addItem({
      command: CommandIDs.checkStartKernel,
      category: 'ipylab',
      rank: 50
    });
    when = settings.load(PLUGIN_ID).then(async () => {
      const config = await settings.get(PLUGIN_ID, 'autostart');
      if (config.composite as boolean) {
        await IpylabModel.JFEM.startIpylabKernel();
      }
    });
    // Handle state restoration.
    if (restorer) {
      void restorer.restore(IpylabModel.tracker, {
        command: CommandIDs.restore,
        args: widget => (widget as any).ipylabSettings,
        name: widget => (widget as any).ipylabSettings.cid,
        when
      });
    }
  }
}
export default extension;
