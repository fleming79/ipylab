# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING

from ipywidgets import TypedTuple
from traitlets import Container, Instance, Union

import ipylab
from ipylab._compat.typing import override
from ipylab.commands import APP_COMMANDS_NAME, CommandRegistry
from ipylab.common import Obj, pack
from ipylab.connection import InfoConnection
from ipylab.ipylab import Ipylab, IpylabBase, Readonly, Transform

if TYPE_CHECKING:
    from asyncio import Task
    from typing import Literal

    from ipylab.commands import CommandConnection
    from ipylab.common import TaskHooks, TransformType


__all__ = ["MenuItemConnection", "MenuConnection", "MainMenu", "ContextMenu"]


class MenuItemConnection(InfoConnection):
    """A connection to an ipylab menu item."""

    menu: Instance[RankedMenu] = Instance("ipylab.menu.RankedMenu")


class RankedMenu(Ipylab):
    """

    ref: https://jupyterlab.readthedocs.io/en/4.0   .x/api/classes/ui_components.RankedMenu.html
    """

    connections: Container[tuple[MenuItemConnection, ...]] = TypedTuple(trait=Instance(MenuItemConnection))

    def add_item(
        self,
        *,
        command: str | CommandConnection = "",
        submenu: MenuConnection | None = None,
        rank=None,
        type: Literal["command", "submenu", "separator"] = "command",  # noqa: A002
        **args,
    ) -> Task[MenuItemConnection]:
        """Add command, subitem or separator.
        **args are 'defaults' used with command only.

        ref: https://jupyterlab.readthedocs.io/en/4.0.x/api/classes/ui_components.RankedMenu.html#addItem.addItem-1
        """
        if isinstance(self, ContextMenu):
            selector = args.pop("selector")
            info = {"rank": rank, "args": args, "type": type, "selector": selector}
        else:
            info = {"rank": rank, "args": args, "type": type}
        to_object = []
        match type:
            case "command":
                if not command:
                    msg = "command is required"
                    raise ValueError(msg)
                info["command"] = str(command)
                info["args"] = args
            case "separator":
                pass
            case "submenu":
                if not isinstance(submenu, MenuConnection):
                    msg = "`submenu` must be an instance of MenuItemConnection"
                    raise TypeError(msg)
                info["submenu"] = submenu
                to_object = ["args[0].submenu"]
            case _:
                msg = f"Invalid type {type}"
                raise ValueError(msg)
        hooks: TaskHooks = {
            "trait_add_fwd": [("info", info), ("menu", self)],
            "close_with_fwd": [self],
            "add_to_tuple_fwd": [(self, "connections")],
        }
        transform: TransformType = {"transform": Transform.connection, "cid": MenuItemConnection.to_cid()}
        return self.execute_method("addItem", info, hooks=hooks, transform=transform, toObject=to_object)

    def activate(self):
        async def activate():
            await ipylab.app.main_menu.set_property("activeMenu", self, toObject=["value"])
            await ipylab.app.main_menu.execute_method("openActiveMenu")

        return self.to_task(activate())


class BuiltinMenu(RankedMenu):
    @override
    def activate(self):
        name = self.ipylab_base[-1].removeprefix("mainMenu.").lower()
        return ipylab.app.commands.execute(f"{name}:open")


class MenuConnection(RankedMenu, InfoConnection):
    """A connection to a custom menu"""

    commands = Instance(CommandRegistry)


class Menu(RankedMenu):
    SINGLE = True

    ipylab_base = IpylabBase(Obj.IpylabModel, "palette").tag(sync=True)

    commands = Instance(CommandRegistry)
    connections: Container[tuple[MenuConnection, ...]] = TypedTuple(
        trait=Union([Instance(MenuConnection), Instance(MenuItemConnection)])
    )

    @classmethod
    @override
    def _single_key(cls, kwgs: dict):
        return cls, kwgs["commands"]

    def __init__(self, *, commands: CommandRegistry, **kwgs):
        commands.close_extras.add(self)
        super().__init__(commands=commands, **kwgs)

    def create_menu(self, label: str, rank: int = 500) -> Task[MenuConnection]:
        "Make a new menu that can be used where a menu is required."
        cid = MenuConnection.to_cid()
        options = {"id": cid, "label": label, "rank": int(rank)}
        hooks: TaskHooks = {
            "trait_add_fwd": [("info", options), ("commands", self.commands)],
            "add_to_tuple_fwd": [(self, "connections")],
            "close_with_fwd": [self],
        }
        return self.execute_method(
            "generateMenu",
            f"{pack(self.commands)}.base",
            options,
            (Obj.this, "translator"),
            obj=Obj.MainMenu,
            toObject=["args[0]", "args[2]"],
            transform={"transform": Transform.connection, "cid": cid},
            hooks=hooks,
        )


class MainMenu(Menu):
    """Direct access to the Jupyterlab main menu.

    ref: https://jupyterlab.readthedocs.io/en/4.0.x/api/classes/mainmenu.MainMenu.html
    """

    SINGLE = True

    ipylab_base = IpylabBase(Obj.IpylabModel, "mainMenu").tag(sync=True)

    file_menu = Readonly(BuiltinMenu, ipylab_base=(Obj.IpylabModel, "mainMenu.fileMenu"))
    edit_menu = Readonly(BuiltinMenu, ipylab_base=(Obj.IpylabModel, "mainMenu.editMenu"))
    view_menu = Readonly(BuiltinMenu, ipylab_base=(Obj.IpylabModel, "mainMenu.viewMenu"))
    run_menu = Readonly(BuiltinMenu, ipylab_base=(Obj.IpylabModel, "mainMenu.runMenu"))
    kernel_menu = Readonly(BuiltinMenu, ipylab_base=(Obj.IpylabModel, "mainMenu.kernelMenu"))
    tabs_menu = Readonly(BuiltinMenu, ipylab_base=(Obj.IpylabModel, "mainMenu.tabsMenu"))
    settings_menu = Readonly(BuiltinMenu, ipylab_base=(Obj.IpylabModel, "mainMenu.settingsMenu"))
    help_menu = Readonly(BuiltinMenu, ipylab_base=(Obj.IpylabModel, "mainMenu.helpMenu"))

    @classmethod
    @override
    def _single_key(cls, kwgs: dict):  # noqa: ARG003
        return cls

    def __init__(self):
        super().__init__(commands=CommandRegistry(name=APP_COMMANDS_NAME))

    def add_menu(self, menu: MenuConnection, *, update=True, rank: int = 500) -> Task[None]:
        """Add a top level menu to the shell.

        ref: https://jupyterlab.readthedocs.io/en/4.0.x/api/classes/mainmenu.MainMenu.html#addMenu
        """
        options = {"rank": rank}
        return self.execute_method("addMenu", menu, update, options, toObject=["args[0]"])

    @override
    def activate(self):
        "Does nothing. Instead you should activate a submenu."


class ContextMenu(Menu):
    """Menu available on mouse right click."""

    SINGLE = True
    # TODO: Support custom context menus.
    # This would require a model similar to CommandRegistryModel.

    ipylab_base = IpylabBase(Obj.IpylabModel, "app.contextMenu").tag(sync=True)

    def add_item(
        self,
        *,
        command: str | CommandConnection = "",
        selector="",
        submenu: MenuConnection | None = None,
        rank=None,
        type: Literal["command", "submenu", "separator"] = "command",  # noqa: A002
        **args,
    ) -> Task[MenuItemConnection]:
        """Add command, subitem or separator.
        **args are 'defaults' used with command only.

        ref: https://jupyterlab.readthedocs.io/en/stable/extension/extension_points.html#context-menu
        """
        add_item_ = super().add_item

        async def add_item():
            return await add_item_(
                command=command,
                selector=selector or ipylab.app.selector,
                submenu=submenu,
                rank=rank,
                type=type,
                **args,
            )

        return self.to_task(add_item())

    @override
    def activate(self):
        "Does nothing for a context menu"
