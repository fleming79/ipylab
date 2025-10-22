// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { IObservableDisposable } from '@lumino/disposable';
import { ISignal, Signal } from '@lumino/signaling';

/**
 * A minimal ObservableDisposable.
 */
export class ObservableDisposable implements IObservableDisposable {
  get disposed(): ISignal<this, void> {
    return this._disposed;
  }

  get isDisposed(): boolean {
    return this._isDisposed;
  }

  dispose(): void {
    if (this.isDisposed) {
      return;
    }
    this._isDisposed = true;
    this._disposed.emit(undefined);
    Signal.clearData(this);
  }

  private _disposed = new Signal<this, void>(this);
  private _isDisposed = false;
}
