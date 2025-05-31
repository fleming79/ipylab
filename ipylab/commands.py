# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import functools
import inspect
import uuid
from typing import TYPE_CHECKING, Any, ClassVar, NotRequired, TypedDict, Unpack

from ipywidgets import TypedTuple
from traitlets import Callable as CallableTrait
from traitlets import Container, Dict, Instance, Tuple, Unicode
from typing_extensions import override

import ipylab
from ipylab.common import IpylabKwgs, Obj, Singular, TransformType, pack
from ipylab.connection import InfoConnection, ShellConnection
from ipylab.ipylab import Ipylab, IpylabBase, Transform, register
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
    command: Instance[CommandConnection] = Instance(InfoConnection)  # type: ignore

    @override
    @classmethod
    def to_id(cls, command: CommandConnection):  # type: ignore
        return super().to_id(str(command), str(uuid.uuid4()))


class CommandConnection(InfoConnection):
    """An Ipylab command registered in a command registry."""

    args = Dict()
    python_command = CallableTrait(allow_none=False)
    namespace_id = Unicode("")

    _config_options: ClassVar = tuple(CommandOptions.__annotations__)
    commands: Instance[CommandRegistry] = Instance("ipylab.commands.CommandRegistry")
    key_bindings: Container[tuple[KeybindingConnection, ...]] = TypedTuple(trait=Instance(KeybindingConnection))

    @override
    @classmethod
    def to_id(cls, command_registry: str, vpath: str, name: str):  # type: ignore
        return super().to_id(command_registry, vpath, name)

    @property
    def repr_info(self):
        return {"name": self.commands.name} | {"info": self.info}

    async def configure(self, *, emit=True, **kwgs: Unpack[CommandOptions]) -> CommandOptions:
        await self.ready()
        if diff := set(kwgs).difference(self._config_options):
            msg = f"The following useless configuration options were detected for {diff} in {self}"
            raise KeyError(msg)

        config: CommandOptions = await self.update_property("config", kwgs)  # type: ignore
        if emit:
            await self.commands.execute_method("commandChanged.emit", ({"id": self.connection_id},))
        return config

    async def add_key_binding(
        self, keys: list, selector="", args: dict | None = None, *, prevent_default=True
    ) -> KeybindingConnection:
        "Add a key binding for this command and selector."
        await self.ready()
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
    def to_id(cls, command: CommandConnection, category: str):  # type: ignore
        return super().to_id(str(command), category)


class CommandPalette(Singular, Ipylab):
    """

    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/apputils.ICommandPalette.html
    """

    ipylab_base = IpylabBase(Obj.IpylabModel, "palette").tag(sync=True)

    info = Dict(help="info about the item")
    connections: Container[tuple[CommandPalletItemConnection, ...]] = TypedTuple(
        trait=Instance("ipylab.commands.CommandPalletItemConnection")
    )

    async def add(
        self, command: CommandConnection, category: str, *, rank=None, args: dict | None = None
    ) -> CommandPalletItemConnection:
        """Add a command to the command pallet (must be registered in this kernel).

        **args are used when calling the command.

        Special args
        ------------
        * ref: ShellConnection | None

        Include `ref` as an argument for function to have the argument provided
        when the command is called via the command registry.

        ref:
            This is a ShellConnection to the current widget in the shell.

            For the command to appear in the context menu non-ipylab widgets,
            the appropriate selector should be used.

            see: https://jupyterlab.readthedocs.io/en/stable/developer/css.html#commonly-used-css-selectors

            Selectors:
                * Notebook: '.jp-Notebook'
                * Main area: '.jp-Activity'

            If the ShellConnection relates to an Ipylab widget. The associated
            widget/panel is accessible as `ref.widget`.
        """
        await self.ready()
        await command.ready()
        if str(command) not in self.app.commands.all_commands:
            msg = f"{command=} is not registered in app command registry app.commands!"
            raise RuntimeError(msg)
        connection_id = CommandPalletItemConnection.to_id(command, category)
        CommandPalletItemConnection.close_if_exists(connection_id)
        info = {"args": args, "category": category, "command": str(command), "rank": rank}
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

    @classmethod
    @override
    def get_single_key(cls, name: str, **kwgs):
        return name

    @property
    def repr_info(self):
        return {"name": self.name}

    def __init__(self, *, name=APP_COMMANDS_NAME, **kwgs):
        super().__init__(name=name, **kwgs)

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        match operation:
            case "execute":
                return await self._execute_for_frontend(payload, buffers)
        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def _execute_for_frontend(self, payload: dict, buffers: list):
        cmd_cid = payload["id"]
        if not CommandConnection.exists(cmd_cid):
            msg = f'Invalid command "{cmd_cid}"'
            raise TypeError(msg)
        conn = await CommandConnection(cmd_cid).ready()
        cmd = conn.python_command
        args = conn.args | (payload.get("args") or {})

        ns = self.app.get_namespace(conn.namespace_id)
        kwgs = {}
        for n, p in inspect.signature(cmd).parameters.items():
            if n == "ref":
                connection_id = payload.get("connection_id")
                kwgs[n] = ShellConnection(connection_id) if connection_id else None
            elif n in args:
                kwgs[n] = args[n]
            elif n in ns:
                kwgs[n] = ns[n]
            elif p.kind is p.VAR_KEYWORD:
                kwgs = args
                break
            elif n == "args":
                kwgs[n] = args
            elif n == "buffers":
                kwgs[n] = buffers
            elif p.default is p.empty:
                msg = f"Required parameter '{n}' missing for {cmd} of {conn}"
                raise NameError(msg)
        ns["_to_eval"] = functools.partial(cmd, **kwgs)
        result = eval("_to_eval()", ns)  # noqa: S307
        while inspect.isawaitable(result):
            result = await result
        return result

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
        namespace_id="",
        **kwgs,
    ) -> CommandConnection:
        """Add a python command that can be executed by Jupyterlab.

        The `connection_id` of the CommnandConnection is used as the `id` in the App
        command registry.

        The `connection_id` is constructed from:

        1. registry name: The name of this command registry [Jupyterlab]
        2. vpath: The virtual 'path' of the app.
        3. name: The name of the command to lookup locally.

        If a connection_id (id) already exists, the existing CommandConnection will be closed prior
        to adding the new command.

        name: str
            A name to use in the id to identify the command.
        execute:

        args: dict | None
            Mapping of default arguments to provide when executing the command.
        kwgs:
            Additional ICommandOptions can be passed as kwgs

        ref: https://lumino.readthedocs.io/en/latest/api/interfaces/commands.CommandRegistry.ICommandOptions.html
        """

        await self.ready()
        app = await self.app.ready()
        connection_id = CommandConnection.to_id(self.name, app.vpath, name)
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
        cc.namespace_id = namespace_id
        cc.python_command = execute
        cc.args = args or {}
        cc.info = kwgs
        cc.add_to_tuple(self, "connections")
        return cc

    async def execute(
        self, command_id: str | CommandConnection, args: dict | None = None, **kwargs: Unpack[IpylabKwgs]
    ):
        """Execute a command registered in the frontend command registry returning
        the result.

        Parameters
        ----------
        command_id: str | CommandConnection
            The id of the command in the command registry or the
            `CommandConnection` of a previously added command.
        args: dict | None
          `args` are used when executing

        see https://github.com/jtpio/ipylab/issues/128#issuecomment-1683097383
        for hints on how to determine what args can be used.
        """
        await self.ready()
        app = await self.app.ready()
        id_ = str(command_id)
        if id_ not in self.all_commands:
            id_ = CommandConnection.to_id(self.name, app.vpath, id_)
            if id_ not in self.all_commands:
                msg = f"Command '{command_id}' not registered!"
                raise ValueError(msg)
        return await self.operation("execute", {"id": id_, "args": args or {}}, **kwargs)

    async def create_menu(self, label: str, rank: int = 500) -> MenuConnection:
        "Make a new menu that can be used where a menu is required."
        await self.ready()
        connection_id = ipylab.menu.MenuConnection.to_id()
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
