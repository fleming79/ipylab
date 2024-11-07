# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any, ClassVar, NotRequired, TypedDict, Unpack

from ipywidgets import TypedTuple
from traitlets import Callable as CallableTrait
from traitlets import Container, Dict, Instance, Tuple, Unicode

import ipylab
from ipylab._compat.typing import override
from ipylab.common import IpylabKwgs, Obj, TaskHooks, TransformType, pack
from ipylab.connection import InfoConnection, ShellConnection
from ipylab.ipylab import Ipylab, IpylabBase, Transform, register
from ipylab.widgets import Icon

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Callable, Coroutine


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


class CommandConnection(InfoConnection):
    """An Ipylab command registered in a command registry."""

    args = Dict()
    python_command = CallableTrait(allow_none=False)
    namespace_name = Unicode("")

    _config_options: ClassVar = tuple(CommandOptions.__annotations__)

    commands: Instance[CommandRegistry] = Instance("ipylab.commands.CommandRegistry")

    @override
    @classmethod
    def to_cid(cls, command_registry: str, vpath: str, name: str):
        return super().to_cid(command_registry, vpath, name)

    @property
    def repr_info(self):
        return {"name": self.commands.name} | {"info": self.info}

    def configure(self, *, emit=True, **kwgs: Unpack[CommandOptions]) -> Task[CommandOptions]:
        if diff := set(kwgs).difference(self._config_options):
            msg = f"The following useless configuration options were detected for {diff} in {self}"
            raise KeyError(msg)

        async def configure():
            config: CommandOptions = await self.update_property("config", kwgs)  # type: ignore
            if emit:
                await self.commands.execute_method("commandChanged.emit", {"id": self.cid})
            return config

        return self.to_task(configure())


class CommandPalletItemConnection(InfoConnection):
    """An Ipylab command palette item."""

    command = Instance(CommandConnection)

    @override
    @classmethod
    def to_cid(cls, command: CommandConnection, category: str):
        return super().to_cid(str(command), category)


class CommandPalette(Ipylab):
    """

    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/apputils.ICommandPalette.html
    """

    SINGLE = True

    ipylab_base = IpylabBase(Obj.IpylabModel, "palette").tag(sync=True)

    info = Dict(help="info about the item")
    connections: Container[tuple[CommandPalletItemConnection, ...]] = TypedTuple(
        trait=Instance("ipylab.commands.CommandPalletItemConnection")
    )

    def add(
        self, command: CommandConnection, category: str, *, rank=None, args: dict | None = None
    ) -> Task[CommandPalletItemConnection]:
        """Add a command to the command pallet (must be registered in this kernel).

        **args are used when calling the command.

        Special args
        ------------

        * active_widget: ShellConnection
        * ref: ShellConnection

        Include in the argument list of the function to have the value provided when the command
        is called.

        active_widget:
            This is a ShellConnection to the Jupyterlab defined active widget.
            For the command to appear in the context menu non-ipylab widgets, the appropriate selector
            should be used. see: https://jupyterlab.readthedocs.io/en/stable/developer/css.html#commonly-used-css-selectors
            Selectors:
                * Notebook: '.jp-Notebook'
                * Main area: '.jp-Activity'

        ref:
            This is a ShellConnection to the Ipylab active widget.
            The associated widget/panel is then accessible by `ref.widget`.

        Tip: This is can be used in context menus to perform actions specific to the active widget
        in the shell.
        """
        cid = CommandPalletItemConnection.to_cid(command, category)
        CommandRegistry._check_belongs_to_application_registry(cid)  # noqa: SLF001
        info = {"args": args, "category": category, "command": str(command), "rank": rank}
        transform: TransformType = {"transform": Transform.connection, "cid": cid}
        hooks: TaskHooks = {
            "add_to_tuple_fwd": [(self, "connections")],
            "trait_add_fwd": [("info", info), ("command", command)],
            "close_with_fwd": [command],
        }
        return self.execute_method("addItem", info, transform=transform, hooks=hooks)


@register
class CommandRegistry(Ipylab):
    SINGLE = True

    _model_name = Unicode("CommandRegistryModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "").tag(sync=True)
    name = Unicode(APP_COMMANDS_NAME, read_only=True).tag(sync=True)
    all_commands = Tuple(read_only=True).tag(sync=True)
    connections: Container[tuple[CommandConnection, ...]] = TypedTuple(trait=Instance(CommandConnection))

    @classmethod
    @override
    def _single_key(cls, kwgs: dict):
        return cls, kwgs["name"]

    @classmethod
    def _check_belongs_to_application_registry(cls, cid: str):
        "Check the cid belongs to the application command registry."
        if APP_COMMANDS_NAME not in cid:
            msg = (
                f"{cid=} doesn't correspond to an ipylab CommandConnection "
                f'for the application command registry "{APP_COMMANDS_NAME}". '
                "Use a command registered with `app.commands.add_command` instead."
            )
            raise ValueError(msg)

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
        conn = InfoConnection.get_existing_connection(payload["id"], quiet=True)
        if not isinstance(conn, CommandConnection):
            msg = f'Invalid command "{payload["id"]} {conn=}"'
            raise TypeError(msg)
        cmd = conn.python_command
        args = conn.args | (payload.get("args") or {}) | {"buffers": buffers}

        # Shell connections
        cids = {"active_widget": payload["cid1"], "ref": payload["cid2"]}

        glbls = ipylab.app.get_namespace(conn.namespace_name)
        kwgs = {}
        for n, p in inspect.signature(cmd).parameters.items():
            if n in ["active_widget", "ref"] and cids[n]:
                kwgs[n] = ShellConnection(cids[n])
                await kwgs[n].ready()
            elif n in args:
                kwgs[n] = args[n]
            elif n in glbls:
                kwgs[n] = glbls[n]
            elif p.kind is p.VAR_KEYWORD:
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

    def add_command(
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

        The `id` in the command registry is the `cid` of the CommnadConnection.
        The `cid` is constructed from:
        1. registry name: The name of this command registry [Jupyterlab]
        2. vpath: The virtual 'path' of the app.
        3. name:

        If a cid (id) already exists, the existing CommandConnection will be closed prior
        to adding the new command.

        name: str
            A name to use in the id to identify the command.
        execute:

        args: dict | None
            Mapping of default arguments to provide.
        kwgs:
            Additional ICommandOptions can be passed as kwgs

        ref: https://lumino.readthedocs.io/en/latest/api/interfaces/commands.CommandRegistry.ICommandOptions.html
        """
        hooks: TaskHooks = {
            "close_with_fwd": [self],
            "add_to_tuple_fwd": [(self, "connections")],
            "trait_add_fwd": [
                ("commands", self),
                ("namespace_name", namespace_name),
                ("python_command", execute),
                ("args", args or {}),
            ],
        }

        async def add_command():
            cid = CommandConnection.to_cid(self.name, ipylab.app.vpath, name)
            if cmd := CommandConnection.get_existing_connection(cid, quiet=True):
                await cmd.ready()
                cmd.close()
            return await self.operation(
                "addCommand",
                id=cid,
                caption=caption,
                label=label or name,
                iconClass=icon_class,
                transform={"transform": Transform.connection, "cid": cid},
                icon=f"{pack(icon)}.labIcon" if isinstance(icon, Icon) else None,
                toObject=["icon"] if isinstance(icon, Icon) else [],
                **kwgs,
            )

        return self.to_task(add_command(), hooks=hooks)

    def execute(self, command_id: str | CommandConnection, args: dict | None = None, **kwgs: Unpack[IpylabKwgs]):
        """Execute a command in the registry.

        `args` are passed to the command.

        see: https://github.com/jtpio/ipylab/issues/128#issuecomment-1683097383 for hints
        about what args can be used.
        """

        async def execute_command():
            id_ = str(command_id)
            if id_ not in self.all_commands:
                id_ = CommandConnection.to_cid(self.name, ipylab.app.vpath, id_)
                if id_ not in self.all_commands:
                    msg = f"Command '{command_id}' not registered!"
                    raise ValueError(msg)
            return await self.operation("execute", id=id_, args=args or {}, **kwgs)

        return self.to_task(execute_command())
