# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

from typing import TYPE_CHECKING

from ipywidgets import TypedTuple
from traitlets import Container, Instance, Unicode, observe

from ipylab.commands import CommandConnection
from ipylab.connection import Connection
from ipylab.ipylab import Ipylab, Transform

if TYPE_CHECKING:
    from asyncio import Task
    from typing import Literal


__all__ = ["MenuItemConnection", "MenuConnection", "MainMenu", "ContextMenu"]


class MenuItemConnection(Connection):
    """A connection to an ipylab menu item.

    ref:
    """

    @observe("comm")
    def _ipylab_observe_comm(self, _):
        if self.comm and (cmd := CommandConnection.get_existing_connection(self.info.get("command", ""), quiet=True)):
            # Dispose when the command is disposed.
            cmd.observe(lambda _: self.close())

    def close(self):
        super().close(dispose=True)


class RankedMenu(Ipylab):
    """

    ref: https://jupyterlab.readthedocs.io/en/4.0   .x/api/classes/ui_components.RankedMenu.html
    """

    items: Container[tuple[MenuItemConnection, ...]] = TypedTuple(trait=Instance(MenuItemConnection))

    @observe("comm")
    def _ipylab_observe_comm(self, _):
        if not self.comm:
            for item in self.items:
                item.close()

    def __new__(cls, *, model_id=None, **kwgs):
        kwgs.pop("basename", None)
        return super().__new__(cls, model_id=model_id, **kwgs)

    def __init__(self, *, model_id=None, basename="", **kwgs):
        if self._async_widget_base_init_complete:
            return
        if basename:
            self.set_trait("_basename", basename)
        super().__init__(model_id=model_id, **kwgs)

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

        as_object = None
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
                as_object = ["args.0.submenu"]
            case _:
                msg = f"Invalid type {type}"
                raise ValueError(msg)
        task = self.execute_method(
            "addItem",
            info,
            transform={
                "transform": Transform.connection,
                "cid": MenuItemConnection.to_cid(),
                "auto_dispose": True,
                "info": info,
            },
            toObject=as_object,
        )
        return self.to_task(self._add_to_tuple_trait("items", task))

    def activate(self):
        async def activate():
            await self.app.main_menu.set_property("activeMenu", self, toObject=["value"])
            await self.app.main_menu.execute_method("openActiveMenu")
            return self

        return self.to_task(activate())


class MenuConnection(RankedMenu, Connection):
    """A connection to a custom menu"""


class MainMenu(Ipylab):
    """Direct access to the Jupyterlab main menu.

    ref: https://jupyterlab.readthedocs.io/en/4.0.x/api/classes/mainmenu.MainMenu.html
    """

    _basename = Unicode("menu").tag(sync=True)
    SINGLETON = True

    edit_menu = Instance(RankedMenu, kw={"basename": "menu.editMenu"})
    file_menu = Instance(RankedMenu, kw={"basename": "menu.fileMenu"})
    kernel_menu = Instance(RankedMenu, kw={"basename": "menu.kernelMenu"})
    run_menu = Instance(RankedMenu, kw={"basename": "menu.runMenu"})
    settings_menu = Instance(RankedMenu, kw={"basename": "menu.settingsMenu"})
    view_menu = Instance(RankedMenu, kw={"basename": "menu.viewMenu"})
    tabs_menu = Instance(RankedMenu, kw={"basename": "menu.tabsMenu"})

    menus: Container[tuple[MenuConnection, ...]] = TypedTuple(trait=Instance(MenuConnection))
    _all_menus: Container[tuple[MenuConnection, ...]] = TypedTuple(trait=Instance(MenuConnection))

    def add_menu(self, label: str, *, update=True, rank: int = 500) -> Task[MenuConnection]:
        """Add a top level menu to the shell.

        ref: https://jupyterlab.readthedocs.io/en/4.0.x/api/classes/mainmenu.MainMenu.html#addMenu
        """
        cid = MenuConnection.to_cid(label)
        task = self._generate_menu(id=cid, label=label, cid=cid, rank=rank)

        async def add_menu():
            menu = await task
            await self.execute_method("addMenu", menu, update, {"rank": rank}, toObject=["args.0"])
            return menu

        return self.to_task(self._add_to_tuple_trait("menus", add_menu()))

    def create_menu(self, label: str, *, rank: int = 500) -> Task[MenuConnection]:
        """Make a new unique menu, likely to be used as a submenu."""
        cid = MenuConnection.to_cid()
        return self._generate_menu(id=f"{cid}|{label}", label=label, cid=cid, rank=rank)

    def _generate_menu(self, *, id: str, label: str, cid: str, rank: int = 500) -> Task[MenuConnection]:  # noqa: A002
        "Make a new menu that can be used where a menu is required."
        if existing := MenuConnection.get_existing_connection(cid, quiet=True):
            existing.close(dispose=True)
        info = {"id": id, "label": label, "rank": int(rank)}
        coro = self.app.schedule_operation(
            "generateMenu",
            options=info,
            transform={"transform": Transform.connection, "cid": cid, "auto_dispose": True, "info": info},
        )
        return self.to_task(self._add_to_tuple_trait("_all_menus", coro))


class ContextMenuConnection(RankedMenu, Connection):
    """A connection to a custom context menu"""


class ContextMenu(RankedMenu):
    """Direct access to the Jupyterlab context menu."""

    _basename = Unicode("app.contextMenu").tag(sync=True)
    SINGLETON = True

    _all_menus: Container[tuple[ContextMenuConnection, ...]] = TypedTuple(trait=Instance(ContextMenuConnection))

    def add_item(
        self,
        *,
        command: str | CommandConnection = "",
        selector=".ipylab-MainArea",
        submenu: MenuConnection | None = None,
        rank=None,
        type: Literal["command", "submenu", "separator"] = "command",  # noqa: A002
        **args,
    ) -> Task[MenuItemConnection]:
        """Add command, subitem or separator.
        **args are 'defaults' used with command only.

        ref: https://jupyterlab.readthedocs.io/en/stable/extension/extension_points.html#context-menu
        """
        return super().add_item(command=command, selector=selector, submenu=submenu, rank=rank, type=type, **args)
