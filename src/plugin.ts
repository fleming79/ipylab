// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { IJupyterWidgetRegistry } from '@jupyter-widgets/base';
import {
  ILabShell,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette } from '@jupyterlab/apputils';
import { IEditorServices } from '@jupyterlab/codeeditor';
import { IDefaultFileBrowser } from '@jupyterlab/filebrowser';
import { ILauncher } from '@jupyterlab/launcher';
import { IMainMenu } from '@jupyterlab/mainmenu';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { ITranslator } from '@jupyterlab/translation';
import { MODULE_NAME, MODULE_VERSION } from './version';
import { INotebookTracker } from '@jupyterlab/notebook';

const PLUGIN_ID = 'ipylab:settings';

/**
 * The default plugin.
 */
const extension: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  autoStart: true,
  requires: [IJupyterWidgetRegistry, IRenderMimeRegistry, IEditorServices],
  optional: [
    ICommandPalette,
    ILabShell,
    IDefaultFileBrowser,
    ILauncher,
    ITranslator,
    IMainMenu,
    INotebookTracker
  ],
  activate: async (
    app: JupyterFrontEnd,
    registry: IJupyterWidgetRegistry,
    rendermime: IRenderMimeRegistry,
    editorServices: IEditorServices,
    palette: ICommandPalette,
    labShell: ILabShell | null,
    defaultBrowser: IDefaultFileBrowser | null,
    launcher: ILauncher | null,
    translator: ITranslator | null,
    mainMenu: IMainMenu | null,
    notebookTracker: INotebookTracker
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
    exports.IpylabModel.editorServices = editorServices;
    exports.IpylabModel.notebookTracker = notebookTracker;

    registry.registerWidget({
      name: MODULE_NAME,
      version: MODULE_VERSION,
      exports
    });
  }
};
export default extension;
