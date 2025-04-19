# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from ipywidgets import TypedTuple
from traitlets import Container, Instance

from ipylab.commands import CommandConnection, CommandPalletItemConnection
from ipylab.common import Obj, Singular, TransformType
from ipylab.ipylab import Ipylab, IpylabBase, Transform

__all__ = ["LauncherConnection"]


class LauncherConnection(CommandPalletItemConnection):
    """An Ipylab launcher item."""


class Launcher(Singular, Ipylab):
    """
    ref: https://jupyterlab.readthedocs.io/en/latest/api/interfaces/launcher.ILauncher-1.html"""

    ipylab_base = IpylabBase(Obj.IpylabModel, "launcher").tag(sync=True)

    connections: Container[tuple[LauncherConnection, ...]] = TypedTuple(trait=Instance(LauncherConnection))

    async def add(self, cmd: CommandConnection, category: str, *, rank=None, **args) -> LauncherConnection:
        """Add a launcher for the command (must be registered in app.commands in this kernel).

        ref: https://jupyterlab.readthedocs.io/en/latest/api/interfaces/launcher.ILauncher.IItemOptions.html
        """
        await self.ready()
        await cmd.ready()
        commands = await self.app.commands.ready()
        if str(cmd) not in commands.all_commands:
            msg = f"{cmd=} is not registered in app command registry app.commands!"
            raise RuntimeError(msg)
        cid = LauncherConnection.to_cid(cmd, category)
        args = {"command": str(cmd), "category": category, "rank": rank, "args": args}
        transform: TransformType = {"transform": Transform.connection, "cid": cid}
        lc: LauncherConnection = await self.execute_method("add", (args,), transform=transform)
        cmd.close_with_self(lc)
        lc.add_to_tuple(self, "connections")
        return lc
