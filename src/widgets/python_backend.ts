import { Session } from '@jupyterlab/services';
import { newSession } from './utils';
import { IpylabModel } from './ipylab';
import { IDisposable } from '@lumino/disposable';
/**
 *  The Python backend that auto loads python side plugins using `pluggy` module.
 *
 */
export class PythonBackendModel {
  async checkStart() {
    if (!this._backendSession || this._backendSession.disposed) {
      this._backendSession = await newSession({
        path: 'Ipylab backend',
        name: 'Ipylab backend',
        language: 'python3',
        code: 'import ipylab.scripts; ipylab.scripts.init_ipylab_backend()'
      });
    }
    // Add a command
    if (!this._command || this._command.isDisposed) {
      this._command = IpylabModel.app.commands.addCommand(
        PythonBackendModel.checkstart,
        {
          label: 'Ipylab check start Python backend',
          caption:
            'Start the Ipylab Python backend that will run registered autostart plugins.\n ' +
            ' in "pyproject.toml"  added entry for: \n' +
            '[project.entry-points.ipylab-python-backend] \n' +
            'autostart = "my_module.ipylab_backend_plugin"',

          execute: () => IpylabModel.python_backend.checkStart()
        }
      );
      if (this._palletItem) {
        this._palletItem.dispose();
      }
      this._palletItem = IpylabModel.palette.addItem({
        command: PythonBackendModel.checkstart,
        category: 'ipylab',
        rank: 500
      });
    }

    return this._backendSession.model;
  }
  static checkstart = 'ipylab:check-start-python-backend';
  private _command?: IDisposable;
  private _palletItem?: IDisposable;
  private _backendSession?: Session.ISessionConnection;
}