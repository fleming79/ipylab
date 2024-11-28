# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING

import ipywidgets

import ipylab
from ipylab.common import IpylabKwgs, hookimpl

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from ipylab import App
    from ipylab.ipylab import Ipylab
    from ipylab.log import IpylabLogHandler


@hookimpl
def launch_jupyterlab():
    import sys

    from jupyterlab.labapp import LabApp

    if not sys.argv:
        sys.argv = ["--ServerApp.token=''"]
    sys.exit(LabApp.launch_instance())


@hookimpl
async def autostart(app: ipylab.App) -> None | Awaitable[None]:
    # Register some default context menu items for Ipylab
    cmd = await app.commands.add_command("Open console", app._context_open_console)  # noqa: SLF001
    await app.context_menu.add_item(command=cmd, rank=70)
    cmd = await app.commands.add_command("Show log viewer", lambda: app.log_viewer.add_to_shell())
    await app.context_menu.add_item(command=cmd, rank=71)


@hookimpl
def opening_console(app: App, args: dict, objects: dict, kwgs: IpylabKwgs):
    "no-op"


@hookimpl
def vpath_getter(app: App, kwgs: dict) -> Awaitable[str] | str:
    return app.dialog.get_text(**kwgs)


@hookimpl
def ready(obj: Ipylab):
    "Pass through"


@hookimpl
def get_log_viewer(app: App, handler: IpylabLogHandler):  # type: ignore
    from ipylab.log_viewer import LogViewer

    return LogViewer(app, handler)


@hookimpl
def default_editor_key_bindings(app: ipylab.App, obj: ipylab.CodeEditor):  # noqa: ARG001
    return {"invoke_completer": ["Ctrl Space"], "evaluate": ["Shift Enter"]}


@hookimpl
def default_namespace_objects(namespace_name: str, app: ipylab.App):
    return {"ipylab": ipylab, "ipw": ipywidgets, "app": app, "namespace_name": namespace_name}
