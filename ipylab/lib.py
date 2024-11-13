# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING

from ipylab.common import IpylabKwgs, hookimpl

if TYPE_CHECKING:
    from collections.abc import Awaitable

    import ipylab
    from ipylab import App
    from ipylab.ipylab import Ipylab


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
    await app.context_menu.add_item(command=cmd, rank=20)
    await app.context_menu.add_item(command="logconsole:open", args={"source": app.vpath}, rank=21)


@hookimpl
def opening_console(app: App, args: dict, objects: dict, kwgs: IpylabKwgs):
    "no-op"


@hookimpl
def vpath_getter(app: App, kwgs: dict) -> Awaitable[str] | str:
    return app.dialog.get_text(**kwgs)


@hookimpl
def ready(obj: Ipylab):
    "Pass through"
