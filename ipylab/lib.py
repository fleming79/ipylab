# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING

from ipylab.common import hookimpl
from ipylab.log import IpylabLogFormatter, IpylabLogHandler

if TYPE_CHECKING:
    from collections.abc import Awaitable

    import ipylab


@hookimpl
def launch_ipylab():
    import sys  # noqa: PLC0415

    from jupyterlab.labapp import LabApp  # noqa: PLC0415

    if not sys.argv:
        sys.argv = ["--IdentityProvider.token=''"]
    sys.exit(LabApp.launch_instance())


@hookimpl
async def autostart(app: ipylab.JupyterFrontEnd) -> None | Awaitable[None]:
    # Register some default context menu items for Ipylab
    # To prevent registering the command use app.DEFAULT_COMMANDS.discard(<name>) in another autostart hookimpl.
    if "Open console" in app.DEFAULT_COMMANDS:
        cmd = await app.commands.add_command("Open console", app.shell.open_console)
        await app.context_menu.add_item(command=cmd, rank=70)
    if "Show log viewer" in app.DEFAULT_COMMANDS:
        cmd = await app.commands.add_command("Show log viewer", app.shell.log_viewer.add_to_shell)
        await app.context_menu.add_item(command=cmd, rank=71)


@hookimpl
async def autostart_once(app: ipylab.JupyterFrontEnd) -> None:
    pass


@hookimpl
async def vpath_getter(app: ipylab.JupyterFrontEnd, kwgs: dict) -> str:
    return await app.dialog.get_text(**kwgs)


@hookimpl
def get_logging_handler(app: ipylab.JupyterFrontEnd) -> IpylabLogHandler:
    fmt = "%(color)s%(level_symbol)s %(asctime)s.%(msecs)d %(name)s {%(filename)s:%(lineno)d} %(owner_rep)s: %(message)s %(reset)s\n"
    handler = IpylabLogHandler(app.log_level)
    handler.setFormatter(IpylabLogFormatter(fmt=fmt, style="%", datefmt="%H:%M:%S"))
    return handler
