# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING

from ipywidgets import TypedTuple
from traitlets import Container, Instance

from ipylab.commands import CommandConnection, CommandPalletItemConnection, CommandRegistry
from ipylab.common import Obj, TaskHooks
from ipylab.connection import Connection
from ipylab.ipylab import Ipylab, IpylabBase, Transform

if TYPE_CHECKING:
    from asyncio import Task


__all__ = ["LauncherConnection"]


class LauncherConnection(CommandPalletItemConnection):
    """An Ipylab launcher item."""


cid: str


class Launcher(Ipylab):
    """
    ref: https://jupyterlab.readthedocs.io/en/latest/api/interfaces/launcher.ILauncher-1.html"""

    SINGLE = True

    ipylab_base = IpylabBase(Obj.IpylabModel, "launcher").tag(sync=True)

    connections: Container[tuple[LauncherConnection, ...]] = TypedTuple(trait=Instance(LauncherConnection))

    def add(self, cmd: CommandConnection, category: str, *, rank=None, **args) -> Task[LauncherConnection]:
        """Add a launcher for the command (must be registered in this kernel).

        ref: https://jupyterlab.readthedocs.io/en/latest/api/interfaces/launcher.ILauncher.IItemOptions.html
        """
        cid = self.remove(cmd, category)
        CommandRegistry._check_belongs_to_application_registry(cid)  # noqa: SLF001
        hooks: TaskHooks = {"close_with_fwd": [cmd], "add_to_tuple_fwd": [(self, "connections")]}
        args = {"command": str(cmd), "category": category, "rank": rank, "args": args}
        return self.execute_method("add", args, transform={"transform": Transform.connection, "cid": cid}, hooks=hooks)

    def remove(self, command: CommandConnection, category: str):
        cid = LauncherConnection.to_cid(command, category)
        if conn := Connection.get_existing_connection(cid, quiet=True):
            conn.close()
        return cid
