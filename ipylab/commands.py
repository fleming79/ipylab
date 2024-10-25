# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, ClassVar, get_args, override

from ipywidgets import TypedTuple
from traitlets import Bool, Container, Dict, ForwardDeclaredInstance, Instance, Tuple, Unicode
from traitlets import Callable as CallableTrait

from ipylab._compat.typing import Any, NotRequired, TypedDict, Unpack
from ipylab.common import IpylabKwgs, Obj, TaskHooks, TransformType, pack
from ipylab.connection import Connection
from ipylab.ipylab import Ipylab, IpylabBase, Transform, register
from ipylab.widgets import Icon

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Callable, Coroutine


__all__ = ["CommandConnection", "CommandPalletItemConnection", "CommandRegistry"]


APP_COMMANDS_NAME = "Jupyterlab"


class CommandOptions(TypedDict):
    caption: NotRequired[str]
    className: NotRequired[str]  # noqa: N815
    dataset: NotRequired[Any]
    describedBy: NotRequired[dict]  # noqa: N815
    iconClass: NotRequired[str]  # noqa: N815
    iconLabel: NotRequired[str]  # noqa: N815
    isEnabled: NotRequired[bool]  # noqa: N815
    isToggled: NotRequired[bool]  # noqa: N815
    isVisible: NotRequired[bool]  # noqa: N815
    label: NotRequired[str]
    mnemonic: NotRequired[str]
    usage: NotRequired[str]


class CommandConnection(Connection):
    """An Ipylab command registered in a command registry."""

    auto_dispose = Bool(True).tag(sync=True)

    info = Dict()
    args = Dict()
    python_command = CallableTrait(allow_none=False)
    namespace_name = Unicode("")

    _config_options: ClassVar = get_args(CommandOptions)

    @override
    @classmethod
    def to_cid(cls, commands_name: str, name: str):
        return super().to_cid(commands_name, name)

    @property
    def commands(self):
        return CommandRegistry(name=self.cid.split(self._SEP)[1])

    def configure(self, *, emit=True, **kwgs: Unpack[CommandOptions]) -> Task[CommandOptions]:
        if diff := set(kwgs).difference(self._config_options):
            msg = f"The following useless configuration options were detected for {diff} in {self}"
            raise KeyError(msg)

        async def configure():
            config: CommandOptions = await self.update_property("config", kwgs)  # type: ignore
            if emit:
                await self.execute_method("commandChanged.emit", {"id": self.cid})
            return config

        return self.to_task(configure())

    def add_launcher(self, category: str, rank=None, **args):
        """Add a launcher for this command.

        **args are used when calling the command.

        When this link is closed the launcher will be disposed.
        """

        return self.to_task(self.app.launcher.add(self, category, rank=rank, **args), hooks={"close_with_rev": [self]})

    def add_to_command_pallet(self, category: str, rank=None, **args):
        """Add a pallet item for this command.

        **args are used when calling the command.

        When this link is closed the pallet item will be disposed.
        """
        return self.to_task(
            self.app.command_pallet.add(self, category, rank=rank, **args), hooks={"close_with_rev": [self]}
        )


class CommandPalletItemConnection(Connection):
    """An Ipylab command palette item."""

    auto_dispose = Bool(True).tag(sync=True)

    @override
    @classmethod
    def to_cid(cls, command: str | CommandConnection, category: str):
        return super().to_cid(str(command), category)


class CommandPalette(Ipylab):
    """

    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/apputils.ICommandPalette.html
    """

    SINGLE = True

    ipylab_base = IpylabBase(Obj.IpylabModel, "palette").tag(sync=True)

    info = Dict(help="info about the item")
    connections: Container[tuple[CommandPalletItemConnection, ...]] = TypedTuple(
        trait=ForwardDeclaredInstance("CommandPalletItemConnection")
    )

    def add(
        self, command: str | CommandConnection, category: str, *, rank=None, args: dict | None = None
    ) -> Task[CommandPalletItemConnection]:
        """Add a command to the command pallet (must be registered in this kernel).

        **args are used when calling the command.
        """
        cid = self.remove(command, category)
        info = {"args": args, "category": category, "command": command, "rank": rank}
        transform: TransformType = {"transform": Transform.connection, "cid": cid}
        hooks: TaskHooks = {"add_to_tuple_fwd": [(self, "connections")], "trait_add_fwd": [(info, "info")]}
        return self.execute_method("addItem", info, transform=transform, hooks=hooks)

    def remove(self, command: str | CommandConnection, category: str):
        cid = CommandPalletItemConnection.to_cid(command, category)
        if conn := CommandPalletItemConnection.get_existing_connection(cid, quiet=True):
            conn.close()
        return cid


@register
class CommandRegistry(Ipylab):
    _model_name = Unicode("CommandRegistryModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "").tag(sync=True)
    name = Unicode(APP_COMMANDS_NAME, read_only=True, help="Use the default registry").tag(sync=True)
    all_commands = Tuple(read_only=True).tag(sync=True)
    connections: Container[tuple[CommandConnection, ...]] = TypedTuple(trait=Instance(CommandConnection))

    @classmethod
    def _single_key(cls, kwgs: dict):
        return cls, kwgs["name"]

    def __init__(self, *, name=APP_COMMANDS_NAME, **kwgs):
        super().__init__(name=name, **kwgs)

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        match operation:
            case "execute":
                return await self._execute_for_frontend(payload, buffers)
        return await super()._do_operation_for_frontend(operation, payload, buffers)

    def add(
        self,
        name: str,
        execute: Callable[..., Coroutine | Any],
        *,
        caption="",
        label="",
        icon_class: str | None = None,
        icon: Icon | None = None,
        args: dict | None = None,
        namespace_name="",
        **kwgs,
    ) -> Task[CommandConnection]:
        """Add a python command that can be executed by Jupyterlab.

        name: str
            The suffix for the 'id'.
        execute:

        args: dict | None
            Mapping of default arguments to provide.
        kwgs:
            Additional ICommandOptions can be passed as kwgs

        ref: https://lumino.readthedocs.io/en/latest/api/interfaces/commands.CommandRegistry.ICommandOptions.html
        """
        cid = self.remove(name)
        hooks: TaskHooks = {
            "add_to_tuple_fwd": [(self, "connections")],
            "trait_add_fwd": [("namespace_name", namespace_name), ("python_command", execute), ("args", args or {})],
        }
        return self.operation(
            "addCommand",
            id=cid,
            caption=caption,
            label=label or name,
            iconClass=icon_class,
            transform={"transform": Transform.connection, "cid": cid},
            icon=f"{pack(icon)}.labIcon" if isinstance(icon, Icon) else None,
            toObject=["icon"] if isinstance(icon, Icon) else (),
            hooks=hooks,
            **kwgs,
        )

    def remove(self, command: str | CommandConnection):
        cid = command.cid if isinstance(command, CommandConnection) else CommandConnection.to_cid(self.name, command)
        if conn := Connection.get_existing_connection(cid, quiet=True):
            conn.close()
        return cid

    async def _execute_for_frontend(self, payload: dict, buffers: list):
        conn = Connection.get_existing_connection(payload["id"], quiet=True)
        if not isinstance(conn, CommandConnection):
            msg = f'Invalid command "{payload["id"]} {conn=}"'
            raise TypeError(msg)
        cmd = conn.python_command
        args = conn.args | (payload.get("args") or {}) | {"buffers": buffers}
        glbls = self.app.get_namespace(conn.namespace_name)
        kwgs = {}
        for n, p in inspect.signature(cmd).parameters.items():
            if n in args:
                kwgs[n] = args[n]
            elif n in glbls:
                kwgs[n] = glbls[n]
            elif p.kind != p.VAR_KEYWORD:
                kwgs = args
                break
            elif p.default is p.empty:
                msg = f"Required parameter '{n}' missing for {cmd} of {conn}"
                raise NameError(msg)
        glbls["_to_eval"] = functools.partial(cmd, **kwgs)
        result = eval("_to_eval()", glbls)  # noqa: S307
        if inspect.isawaitable(result):
            result = await result
        return result

    def execute(self, command_id: str | CommandConnection, args: dict | None = None, **kwgs: Unpack[IpylabKwgs]):
        """Execute a command in the registry.

        `args` are passed to the command.

        see: https://github.com/jtpio/ipylab/issues/128#issuecomment-1683097383 for hints
        about what args can be used.
        """

        async def execute_command():
            id_ = str(command_id)
            async with self as cmd:
                if id_ not in cmd.all_commands:
                    id_ = CommandConnection.to_cid(cmd.name, id_)
                    if id_ not in cmd.all_commands:
                        msg = f"Command '{command_id}' not registered!"
                        raise ValueError(msg)
                return await cmd.operation("execute", id=id_, args=args or {}, **kwgs)

        return self.to_task(execute_command())
