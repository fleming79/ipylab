# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pluggy

hookspec = pluggy.HookspecMarker("ipylab")

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from ipylab import App, Ipylab
    from ipylab.common import ErrorSource, IpylabKwgs


@hookspec(firstresult=True)
def start_app(vpath: str) -> App:  # type: ignore
    "Start the App"


@hookspec()
def ready(obj: Ipylab) -> None | Awaitable[None]:
    """
    Called for each object that is ready.

    Return a coro or awaitable for it to run as a task in the obj.
    """


@hookspec(historic=True)
async def autostart(app: App) -> None | Awaitable[None]:
    """
    Called inside each Python kernel when the frontend is 'ready'.

    Use this with modules that define entry points.

    To run in the Ipylab kernel exclusively use.

    ``` python
    if not app.is_ipylab_kernel:
        return
    ```

    Historic
    --------

    This plugin is historic so will activate when a plugin is registered after
    the app is ready.
    """


@hookspec(firstresult=True)
def autostart_result(app: App, result: Awaitable | None) -> None | Literal[True]:
    "Called with the result of autostart (firstresult=True)."
    # We use underscore so it is registered first


@hookspec(firstresult=True)
def namespace_objects(objects: dict, namespace_name: str, app: App) -> None:
    "Set objects that are available by default in the namespace (firstresult=True)."


@hookspec(firstresult=True)
def on_error(obj: Ipylab, source: ErrorSource, error: Exception):
    """
    Intercept an error message for logging purposes (firstresult=True).

    Fired when an exception occurs trying to process a message from the frontend.

    Args
    ----

    obj: Ipylab
        The object from where the error.

    aw: Awaitable
        The awaitable object running in the task.

    error: Exception
        The exception.
    """


@hookspec
def opening_console(app: App, args: dict, objects: dict, kwgs: IpylabKwgs) -> None | Awaitable[None]:
    """
    Called when the console is opening.

    Add or remove items from the dicts to alter loading of console.

    Returned awaitables will be awaited prior to proceeding.

    Args
    ----

    app: App

    The Ipylab widget that owns the shell connection if there is one.

    args: dict
        options used with `open_console`.
        keys: [activate, ref (as id), insertMode, type]

    objects: dict
        objects for loading into the namespace.
        'ref:(as ShellConnection) is used as the ref for options. This must be a ShellConnection or None.

    kwgs:IpylabKwgs
        Added keys 'namesapace_name' the name of the name space to load.
    """


@hookspec(firstresult=True)
def vpath_getter(app: App, kwgs: dict) -> Awaitable[str] | str:  # type: ignore
    """
    Resolve with a request for a vpath (firstresult=True).
    """


@hookspec
def task_result(obj: Ipylab, result, aw: Awaitable, hooks: dict):
    """
    Called with the result of a task.

    This is used by ipylab to provide `TaskHooks` to set traits between related objects."""
