# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pluggy

hookspec = pluggy.HookspecMarker("ipylab")

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import ipylab
    from ipylab.common import ErrorSource, IpylabFrontendError, IpylabKwgs


@hookspec(firstresult=True)
def launch_jupyterlab():
    "Start Jupyterlab"


@hookspec()
def ready(obj: ipylab.Ipylab) -> None | Awaitable[None]:
    """
    Called by `obj` when it is ready.

    Return a coro or awaitable for it to run as a new task belonging to obj.
    """


@hookspec(historic=True)
async def autostart(app: ipylab.App) -> None | Awaitable[None]:
    """
    Called when the `app` is ready.

    Historic
    --------

    This plugin is historic so will be called when a plugin is registered if the
    app is already ready.
    """


@hookspec(firstresult=True)
def ensure_run(obj: ipylab.Ipylab, aw: Callable | Awaitable | None) -> None | Literal[True]:
    """
    Used by ipylab to ensure 'aw' has been run.

    see lib.ensure_run for further detail.
    """


@hookspec(firstresult=True)
def namespace_objects(objects: dict, namespace_name: str, app: ipylab.App) -> None:
    """
    Called when loading a namespace.

    You can use this to customise the objects available in the namespace."""


@hookspec(firstresult=True)
def on_error(obj: ipylab.Ipylab, source: ErrorSource, error: Exception):
    """
    Intercept an error message for logging purposes.

    Fired when an exception occurs trying to process a message from the frontend.

    Args
    ----

    obj: ipylab.Ipylab
        The object from where the error.

    aw: Awaitable
        The awaitable object running in the task.

    error: Exception
        The exception.
    """


@hookspec
def opening_console(app: ipylab.App, args: dict, objects: dict, kwgs: IpylabKwgs) -> None | Awaitable[None]:
    """
    Called when the console is opening.

    Alter the contents of the dicts as required to adjust the namespace of the console.

    Returned awaitables will be awaited prior to proceeding.

    Args
    ----

    app: ipylab.App

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
def vpath_getter(app: ipylab.App, kwgs: dict) -> Awaitable[str] | str:  # type: ignore
    """
    Resolve with a request for a vpath.

    This is used in conjunction with `app.shell.add` enabling customisation of the vpath.

    vpath is the 'virtual path' for a session.
    """


@hookspec
def task_result(obj: ipylab.Ipylab, result, aw: Awaitable, hooks: dict):
    """
    Called with the result of a task.

    This is used by ipylab to provide `TaskHooks` to set traits between related objects."""


@hookspec(firstresult=True)
def to_frontend_error(obj: ipylab.Ipylab, content: dict) -> IpylabFrontendError:  # type: ignore
    "Make a new IpylabFrontendError"
