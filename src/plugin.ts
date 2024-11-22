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
import { IMainMenu } from '@jupyterlab/mainmenu';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { ISettingRegistry } from '@jupyterlab/settingregistry';
import { ITranslator } from '@jupyterlab/translation';
import { MODULE_NAME, MODULE_VERSION } from './version';

const PLUGIN_ID = 'ipylab:settings';

/**
 * The command IDs used by the plugin.
 */
namespace CommandIDs {
  export const restore = 'ipylab:restore';
  export const checkStartKernel = 'ipylab:check-start-kernel';
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
    IMainMenu
  ],
  activate: async (
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
    mainMenu: IMainMenu | null
  ) => {
    // add globals
    const exports = await import('./widget');

    exports.IpylabModel.app = app;
    exports.IpylabModel.rendermime = rendermime;
    exports.IpylabModel.labShell = labShell;
    exports.IpylabModel.defaultBrowser = defaultBrowser;
    exports.IpylabModel.palette = palette;
    exports.IpylabModel.translator = translator;
    exports.IpylabModel.launcher = launcher;
    exports.IpylabModel.mainMenu = mainMenu;

    registry.registerWidget({
      name: MODULE_NAME,
      version: MODULE_VERSION,
      exports
    });

    let when;
    if (exports.IpylabModel.PER_KERNEL_WM) {
      app.commands.addCommand(CommandIDs.restore, {
        execute: exports.ShellModel.restoreToShell
      });
      app.commands.addCommand(CommandIDs.checkStartKernel, {
        label: 'Start or restart ipylab kernel',
        caption: 'Start or restart  the python kernel with path="ipylab".',
        execute: () => exports.JupyterFrontEndModel.startIpylabKernel(true)
      });

      palette.addItem({
        command: CommandIDs.checkStartKernel,
        category: 'ipylab',
        rank: 50
      });
      when = settings.load(PLUGIN_ID).then(async () => {
        const config = await settings.get(PLUGIN_ID, 'autostart');
        if (config.composite as boolean) {
          await exports.JupyterFrontEndModel.startIpylabKernel();
        }
      });
      // Handle state restoration.
      if (restorer) {
        void restorer.restore(exports.IpylabModel.tracker, {
          command: CommandIDs.restore,
          args: widget => (widget as any).ipylabSettings,
          name: widget => (widget as any).ipylabSettings.cid,
          when
        });
      }
    }
  }
};
export default extension;
