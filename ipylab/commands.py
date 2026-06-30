# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, ClassVar, NotRequired, TypedDict, Unpack

import async_kernel
from aiologic import BinarySemaphore
from async_kernel.common import Fixed
from ipywidgets import TypedTuple
from ipywidgets.widgets.widget import register
from traitlets import Callable as CallableTrait
from traitlets import Container, Dict, Instance, Tuple, Unicode
from typing_extensions import override

import ipylab
from ipylab.common import IpylabKwgs, Obj, Singular, Transform, TransformType, execute_using_shells_namespace, pack
from ipylab.connection import InfoConnection
from ipylab.ipylab import Ipylab, IpylabBase
from ipylab.widgets import Icon

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from ipylab.menu import MenuConnection


__all__ = ["CommandConnection", "CommandPalletItemConnection", "CommandRegistry"]


APP_COMMANDS_NAME = "Jupyterlab"


class CommandOptions(TypedDict):
    caption: NotRequired[str]
    className: NotRequired[str]
    dataset: NotRequired[Any]
    describedBy: NotRequired[dict]
    iconClass: NotRequired[str]
    iconLabel: NotRequired[str]
    isEnabled: NotRequired[bool]
    isToggled: NotRequired[bool]
    isVisible: NotRequired[bool]
    label: NotRequired[str]
    mnemonic: NotRequired[str]
    usage: NotRequired[str]


class KeybindingConnection(InfoConnection):
    command = Instance(InfoConnection)

    @override
    @classmethod
    def to_id(cls, command: CommandConnection) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        return super().to_id(str(command), str(uuid.uuid4()))


class CommandConnection(InfoConnection):
    """An Ipylab command registered in a command registry."""

    args = Dict()
    python_command = CallableTrait(allow_none=False)

    _config_options: ClassVar = tuple(CommandOptions.__annotations__)
    commands: Instance[CommandRegistry] = Instance("ipylab.commands.CommandRegistry")
    key_bindings: Container[tuple[KeybindingConnection, ...]] = TypedTuple(trait=Instance(KeybindingConnection))

    @classmethod
    @override
    def to_id(cls, command_registry: str, vpath: str, name: str) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        return super().to_id(command_registry, vpath, name)

    @property
    @override
    def repr_info(self) -> dict[str, Any]:
        return {"info": self.info}

    async def configure(self, *, emit=True, **kwgs: Unpack[CommandOptions]) -> CommandOptions:
        await self.wait_ready()
        if diff := set(kwgs).difference(self._config_options):
            msg = f"The following useless configuration options were detected for {diff} in {self}"
            raise KeyError(msg)

        config: CommandOptions = await self.update_property(subpath="config", value=kwgs)  # pyright: ignore[reportAssignmentType, reportArgumentType]
        if emit:
            await self.commands.execute_method("commandChanged.emit", ({"id": self.connection_id},))
        return config

    async def add_key_binding(
        self, keys: list, selector="", args: dict | None = None, *, prevent_default=True
    ) -> KeybindingConnection:
        "Add a key binding for this command and selector."
        await self.wait_ready()
        args = args or {} | {
            "keys": keys,
            "preventDefault": prevent_default,
            "selector": selector or self.app.selector,
            "command": str(self),
        }
        connection_id = KeybindingConnection.to_id(self)
        KeybindingConnection.close_if_exists(connection_id)
        transform: TransformType = {"transform": Transform.connection, "connection_id": connection_id}
        kb: KeybindingConnection = await self.commands.execute_method("addKeyBinding", (args,), transform=transform)
        kb.add_to_tuple(self, "key_bindings")
        kb.info = args
        kb.command = self
        self.close_with_self(kb)
        return kb


class CommandPalletItemConnection(InfoConnection):
    """An Ipylab command palette item."""

    command = Instance(CommandConnection)

    @override
    @classmethod
    def to_id(cls, command: CommandConnection, category: str) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        return super().to_id(str(command), category)


class CommandPalette(Singular, Ipylab):
    """A CommandPallet [ref](https://jupyterlab.readthedocs.io/en/latest/api/interfaces/apputils.ICommandPalette.html)."""

    ipylab_base = IpylabBase(Obj.IpylabModel, "palette").tag(sync=True)

    info = Dict(help="info about the item")
    connections: Container[tuple[CommandPalletItemConnection, ...]] = TypedTuple(
        trait=Instance("ipylab.commands.CommandPalletItemConnection")
    )

    async def add(
        self, command: CommandConnection, category: str, *, rank=None, args: dict | None = None
    ) -> CommandPalletItemConnection:
        """
        Add a command to the command pallet [ref](https://jupyterlab.readthedocs.io/en/latest/api/interfaces/apputils.IPaletteItem.html).

        Args:
            command: The command to add to the pallet.
            category: The for the command.
            rank: The rank is used as a tie-breaker when ordering command items for display.
            args: The args to use when calling the command.
        """
        await self.wait_ready()
        cmd = await self.app.commands.validate_command_id(command)
        connection_id = CommandPalletItemConnection.to_id(command, category)
        CommandPalletItemConnection.close_if_exists(connection_id)
        info = {"args": args, "category": category, "command": cmd, "rank": rank}
        transform: TransformType = {"transform": Transform.connection, "connection_id": connection_id}
        cpc: CommandPalletItemConnection = await self.execute_method("addItem", (info,), transform=transform)
        self.close_with_self(cpc)
        cpc.add_to_tuple(self, "connections")
        cpc.info = info
        cpc.command = command
        return cpc


@register
class CommandRegistry(Singular, Ipylab):
    _model_name = Unicode("CommandRegistryModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "").tag(sync=True)
    name = Unicode(APP_COMMANDS_NAME, read_only=True).tag(sync=True)
    all_commands = Tuple(read_only=True).tag(sync=True)
    connections: Container[tuple[InfoConnection, ...]] = TypedTuple(trait=Instance(InfoConnection))
    _lock = Fixed(BinarySemaphore)

    @classmethod
    @override
    def get_single_key(cls, name: str, **kwgs) -> str:
        return name

    @property
    @override
    def repr_info(self):
        return {"name": self.name}

    def __init__(self, *, name=APP_COMMANDS_NAME, **kwgs):
        super().__init__(name=name, **kwgs)

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        match operation:
            case "execute":
                cmd_id = payload["id"]
                if not CommandConnection.exists(cmd_id):
                    msg = f'Invalid command "{cmd_id}"'
                    raise TypeError(msg)
                conn = await CommandConnection(cmd_id).wait_ready()
                options = conn.args | (payload.get("args") or {})
                with async_kernel.utils.subshell_context(options.get("subshell_id")):
                    return await execute_using_shells_namespace(
                        conn.python_command, self.app.kernel.shell, options, connection_id=payload.get("connection_id")
                    )
            case _:
                pass

        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def add_command(
        self,
        name: str,
        execute: Callable[..., Coroutine | Any],
        *,
        caption="",
        label="",
        icon_class: str | None = None,
        icon: Icon | None = None,
        args: dict | None = None,
        **kwgs,
    ) -> CommandConnection:
        """
        Add a python command that can be executed by Jupyterlab [ref](https://lumino.readthedocs.io/en/latest/api/interfaces/commands.CommandRegistry.ICommandOptions.html).

        Args:
            name: The name to use when forming the command id.
            execute: The python callback.
            args: A mapping of default arguments to provide when executing the command.
            kwgs:
                Additional ICommandOptions can be passed as kwgs.
        """

        await self.wait_ready()
        async with self._lock:
            connection_id = CommandConnection.to_id(self.name, self.app.vpath, name)
            CommandConnection.close_if_exists(connection_id)
            kwgs = kwgs | {
                "id": connection_id,
                "connection_id": connection_id,
                "caption": caption,
                "label": label or name,
                "iconClass": icon_class,
                "icon": f"{pack(icon)}.labIcon" if isinstance(icon, Icon) else None,
            }
            cc: CommandConnection = await self.operation(
                "addCommand",
                kwgs,
                transform={"transform": Transform.connection, "connection_id": connection_id},
                toObject=["icon"] if isinstance(icon, Icon) else [],
            )
            self.close_with_self(cc)
            cc.commands = self
            cc.python_command = execute
            cc.args = args or {}
            cc.info = kwgs
            cc.add_to_tuple(self, "connections")
            return cc

    async def validate_command_id(self, cmd: str | CommandConnection) -> str:
        if isinstance(cmd, CommandConnection):
            await cmd.wait_ready()
        cmd = str(cmd)
        if cmd not in self.all_commands:
            cmd = CommandConnection.to_id(self.name, self.app.vpath, cmd)
            if cmd not in self.all_commands:
                msg = f"Command '{cmd}' not registered!"
                raise ValueError(msg)
        return cmd

    async def execute(
        self, command_id: str | CommandConnection, args: dict | None = None, **kwargs: Unpack[IpylabKwgs]
    ) -> Any:
        """
        Execute a command registered in the frontend command registry returning the result.

        See [issue](https://github.com/jtpio/ipylab/issues/128#issuecomment-1683097383) for hints on how to determine what args can be used.

        Args:
            command_id: The id of the command in the command registry or the `CommandConnection` of a previously added command.
            args: `args` are used when executing.
        """
        await self.wait_ready()

        id_ = await self.validate_command_id(str(command_id))
        return await self.operation("execute", {"id": id_, "args": args or {}}, **kwargs)

    async def create_menu(self, label: str, rank: int = 500) -> MenuConnection:
        "Create a new menu that can be used anywhere a menu is required."
        await self.wait_ready()
        connection_id = ipylab.menu.MenuConnection.to_id()
        async with self._lock:
            ipylab.menu.MenuConnection.close_if_exists(connection_id)
            options = {"id": connection_id, "label": label, "rank": int(rank)}
            mc: MenuConnection = await self.execute_method(
                "generateMenu",
                (f"{pack(self)}.base", options, (Obj.this, "translator")),
                obj=Obj.MainMenu,
                toObject=["args[0]", "args[2]"],
                transform={"transform": Transform.connection, "connection_id": connection_id},
            )
            self.close_with_self(mc)
            mc.info = options
            mc.commands = self
            mc.add_to_tuple(self, "connections")
            return mc

    async def described_by(self, command_id: str | CommandConnection) -> dict[str, Any]:
        "Get a description of a specific command [ref](https://lumino.readthedocs.io/en/latest/api/classes/commands.CommandRegistry-1.html#describedBy)."
        id_ = await self.validate_command_id(command_id)
        return await self.execute_method("describedBy", (id_,))
