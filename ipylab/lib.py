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


@hookimpl
def launch_ipylab():
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
async def autostart_once(app: ipylab.App) -> None:
    pass


@hookimpl
async def vpath_getter(app: App, kwgs: dict) -> str:
    return await app.dialog.get_text(**kwgs)


@hookimpl
def default_namespace_objects(namespace_id: str, app: ipylab.App) -> dict:
    return {"ipylab": ipylab, "ipw": ipywidgets, "app": app, "namespace_id": namespace_id}


@hookimpl
def get_asyncio_event_loop(app: ipylab.App):
    try:
        return app.comm.kernel.asyncio_event_loop  # type: ignore
    except AttributeError:
        import asyncio

        return asyncio.get_running_loop()
