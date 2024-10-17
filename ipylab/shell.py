# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

from typing import TYPE_CHECKING

from ipywidgets import TypedTuple, Widget
from traitlets import Container, Instance, Unicode

import ipylab
from ipylab import Area, Connection, InsertMode, Ipylab, ShellConnection, Transform, pack

if TYPE_CHECKING:
    import inspect
    from asyncio import Task
    from typing import Literal


__all__ = ["Shell"]


class Shell(Ipylab):
    """
    Provides access to the shell.
    The minimal interface is:
    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/application.App.IShell.html

    Likely the full labShell interface.

    ref: https://jupyterlab.readthedocs.io/en/latest/api/interfaces/application.App.IShell.html#add
    """

    SINGLETON = True
    _model_name = Unicode("ShellModel", help="Name of the model.", read_only=True).tag(sync=True)
    _basename = Unicode("shell").tag(sync=True)

    connections: Container[tuple[ShellConnection, ...]] = TypedTuple(trait=Instance(ShellConnection))

    def _on_frontend_init(self):
        return super()._on_frontend_init()

    def add(
        self,
        obj: Widget | inspect._SourceObjectType,
        *,
        area: Area = Area.main,
        activate: bool = True,
        mode: InsertMode = InsertMode.tab_after,
        rank: int | None = None,
        ref: ShellConnection | None = None,
        options: dict | None = None,
        cid: str = "",
        vpath: str | dict[Literal["title"], str] = "",
        **kwgs,
    ) -> Task[ShellConnection]:
        """
        Add a widget or evaluation to the
        [shell](https://jupyterlab.readthedocs.io/en/latest/api/interfaces/application.App.IShell.html#add).

        obj
        ---

        When `obj` is NOT a Widget it is assumed `obj` should be evaluated in a python kernel.
            vpath: str | dict[literal['title':str]]
                **Only relevant for 'evaluate'**
                The 'virtual' path for the app. A new kernel will be created if a session
                doesn't exist with the same path.
                If a dict is provided, a text_dialog will be used to obtain the vpath.

            Note:
            The result (payload) of evaluate must be a Widget with a view and NOT a ShellConnection.


        options: dict
            mode: InsertMode
            https://jupyterlab.readthedocs.io/en/latest/api/interfaces/docregistry.DocumentRegistry.IOpenOptions.html

        Basic example
        -------------

        The example evaluates code in a session with path="test". A new kernel is started if a
        session doesn't exist that has a path = vpath.
        ```
        app.shell.add("ipylab.Panel([ipw.HTML('<h1>Test')])", vpath="test")
        ```
        """

        kwgs["options"] = {
            "activate": activate,
            "mode": InsertMode(mode),
            "rank": int(rank) if rank else None,
            "ref": ref.id if isinstance(ref, Connection) else None,
        } | (options or {})

        if isinstance(obj, ShellConnection):
            if cid and cid != obj.cid:
                msg = f"The provided {cid=} does not match {obj.cid=}"
                raise RuntimeError(msg)
            kwgs["id"] = obj.id
        elif isinstance(obj, Widget):
            if not obj._view_name:  # noqa: SLF001
                msg = f"This widget does not have a view {obj}"
                raise RuntimeError(msg)
            if not cid:
                for c in self.connections:
                    if c.widget is obj:
                        cid = c.cid
                        break
            kwgs["ipy_model"] = obj.model_id
        else:
            kwgs["evaluate"] = pack(obj)

        cid = ShellConnection.to_cid(cid)
        conn = ShellConnection(cid)
        if isinstance(obj, Widget) and obj._view_name:  # noqa: SLF001
            conn.set_trait("widget", obj)

        async def add_to_shell():
            if "evaluate" in kwgs:
                if isinstance(vpath, dict):
                    kwgs["vpath"] = await self.app.dialog.get_text(vpath["title"])
                else:
                    kwgs["vpath"] = vpath or self.app.vpath

            conn_ = await self.operation(
                "addToShell",
                area=area,
                transform={"transform": Transform.connection, "cid": cid},
                cid=cid,
                **kwgs,
            )
            assert conn_ is conn  # noqa: S101
            await self._add_to_tuple_trait(self, "connections", conn)
            if isinstance(obj, ipylab.Panel):
                await self._add_to_tuple_trait(obj, "connections", conn)

            return conn

        return self.app.to_task(add_to_shell())

    def expand_left(self):
        return self.execute_method("expandLeft")

    def expand_right(self):
        return self.execute_method("expandRight")

    def collapse_left(self):
        return self.execute_method("collapseLeft")

    def collapse_right(self):
        return self.execute_method("collapseRight")
