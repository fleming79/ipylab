# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING

import ipywidgets

import ipylab
from ipylab.common import hookimpl

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from ipylab import App
    from ipylab.ipylab import Ipylab


@hookimpl
def launch_jupyterlab():
    import sys

    from jupyterlab.labapp import LabApp

    if not sys.argv:
        sys.argv = ["--IdentityProvider.token=''"]
    sys.exit(LabApp.launch_instance())


@hookimpl
async def autostart(app: ipylab.App) -> None | Awaitable[None]:
    # Register some default context menu items for Ipylab
    # To prevent registering the command use app.DEFAULT_COMMANDS.discard(<name>) in another autostart hookimpl.
    if "Open console" in app.DEFAULT_COMMANDS:
        cmd = await app.commands.add_command("Open console", app.shell.open_console)
        await app.context_menu.add_item(command=cmd, rank=70)
    if "Show log viewer" in app.DEFAULT_COMMANDS:
        cmd = await app.commands.add_command("Show log viewer", app.shell.log_viewer.add_to_shell)
        await app.context_menu.add_item(command=cmd, rank=71)


@hookimpl
def vpath_getter(app: App, kwgs: dict) -> Awaitable[str] | str:
    return app.dialog.get_text(**kwgs)


@hookimpl
def ready(obj: Ipylab):
    "Pass through"


@hookimpl
def default_editor_key_bindings(app: ipylab.App, obj: ipylab.CodeEditor):  # noqa: ARG001
    return {}


@hookimpl
def default_namespace_objects(namespace_id: str, app: ipylab.App):
    return {"ipylab": ipylab, "ipw": ipywidgets, "app": app, "namespace_id": namespace_id}
