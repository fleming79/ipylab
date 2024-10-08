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
import { ITranslator } from '@jupyterlab/translation';
import { MODULE_NAME, MODULE_VERSION } from './version';
import { IpylabModel, JupyterFrontEndModel } from './widget';
import { IpylabAutostart } from './widgets/autostart';
const EXTENSION_ID = 'ipylab:plugin';

/**
 * The default plugin.
 */
const extension: JupyterFrontEndPlugin<void> = {
  id: EXTENSION_ID,
  autoStart: true,
  requires: [IJupyterWidgetRegistry, IRenderMimeRegistry],
  optional: [
    ILayoutRestorer,
    ICommandPalette,
    ILabShell,
    IDefaultFileBrowser,
    ILauncher,
    ITranslator,
    IMainMenu
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
  restorer: ILayoutRestorer,
  palette: ICommandPalette,
  labShell: ILabShell | null,
  defaultBrowser: IDefaultFileBrowser | null,
  launcher: ILauncher | null,
  translator: ITranslator | null,
  menu: IMainMenu | null
): Promise<void> {
  const widgetExports = await import('./widget');
  if (!widgetExports.JupyterFrontEndModel.app) {
    // add globals
    widgetExports.IpylabModel.app = app;
    widgetExports.IpylabModel.rendermime = rendermime;
    widgetExports.IpylabModel.labShell = labShell;
    widgetExports.IpylabModel.defaultBrowser = defaultBrowser;
    widgetExports.IpylabModel.palette = palette;
    widgetExports.IpylabModel.translator = translator;
    widgetExports.IpylabModel.launcher = launcher;
    widgetExports.IpylabModel.menu = menu;
    widgetExports.IpylabModel.exports = {
      name: MODULE_NAME,
      version: MODULE_VERSION,
      exports: widgetExports
    };

    registry.registerWidget(widgetExports.IpylabModel.exports);
  }
  app.commands.addCommand('ipylab:add-to-shell', {
    execute: JupyterFrontEndModel.addToShell
  });
  app.commands.addCommand('ipylab:restore', {
    execute: JupyterFrontEndModel.restoreToShell
  });
  app.commands.addCommand('ipylab:open-console', {
    execute: JupyterFrontEndModel.openConsole,
    label: 'Open console'
  });
  app.contextMenu.addItem({
    command: 'ipylab:open-console',
    selector: '.ipylab-MainArea',
    rank: 1
  });

  IpylabAutostart.checkStart();
  // Handle state restoration.
  if (restorer) {
    void restorer.restore(IpylabModel.tracker, {
      command: 'ipylab:restore',
      args: widget => (widget as any).ipylabSettings,
      name: widget => (widget as any).ipylabSettings.cid,
      when: IpylabModel.ipylabKernelReady.promise
    });
  }
}

export default extension;
