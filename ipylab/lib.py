# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING

import ipywidgets

import ipylab
from ipylab.common import InsertMode, hookimpl

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

    def open_console(ref: ipylab.ShellConnection | None, current_widget: ipylab.ShellConnection | None, args: dict):
        app.ensure_run(
            ipylab.plugin_manager.hook.open_console(app=app, ref=ref, current_widget=current_widget, args=args)
        )

    cmd = await app.commands.add_command("Open console", open_console)
    await app.context_menu.add_item(command=cmd, rank=70)
    cmd = await app.commands.add_command("Show log viewer", lambda: app.log_viewer.add_to_shell())
    await app.context_menu.add_item(command=cmd, rank=71)


@hookimpl
def open_console(
    app: ipylab.App, ref: ipylab.ShellConnection | None, current_widget: ipylab.ShellConnection | None, args: dict
):
    args = {"path": app.vpath, "insertMode": InsertMode.split_bottom, "activate": True} | (args or {})

    async def _open_console():
        conn: ipylab.ShellConnection = await app.commands.execute("console:open", args)
        conn.add_to_tuple(app.shell, "connections")
        if ref:
            app.push_namespace_to_shell({"ref": ref, "current_widget": current_widget})
        return conn

    return _open_console()


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
    return {"invoke_completer": ["Tab"], "evaluate": ["Shift Enter"]}


@hookimpl
def default_namespace_objects(namespace_name: str, app: ipylab.App):
    return {"ipylab": ipylab, "ipw": ipywidgets, "app": app, "namespace_name": namespace_name}
