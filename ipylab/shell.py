# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import contextlib
import inspect
from typing import TYPE_CHECKING, Unpack

from ipywidgets import DOMWidget, TypedTuple, Widget
from traitlets import Container, Instance, Unicode

import ipylab
from ipylab import Area, InsertMode, Ipylab, ShellConnection, Transform, pack
from ipylab.common import Fixed, IpylabKwgs, Obj, Singular, TransformType
from ipylab.ipylab import IpylabBase
from ipylab.log_viewer import LogViewer

if TYPE_CHECKING:
    from typing import Literal


__all__ = ["Shell", "ConsoleConnection"]


class ConsoleConnection(ShellConnection):
    "A connection intended for a JupyterConsole"


class Shell(Singular, Ipylab):
    """Provides access to the shell."""

    _model_name = Unicode("ShellModel", help="Name of the model.", read_only=True).tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app.shell").tag(sync=True)
    current_widget_id = Unicode(read_only=True).tag(sync=True)

    log_viewer = Fixed(LogViewer)

    connections: Container[tuple[ShellConnection, ...]] = TypedTuple(trait=Instance(ShellConnection))
    console: Instance[ConsoleConnection | None] = Instance(ConsoleConnection, default_value=None, allow_none=True)  # type: ignore

    async def add(
        self,
        obj: Widget | inspect._SourceObjectType,
        *,
        area: Area = Area.main,
        activate: bool = True,
        mode: InsertMode = InsertMode.tab_after,
        rank: int | None = None,
        ref: ShellConnection | None = None,
        options: dict | None = None,
        vpath: str | dict[Literal["title"], str] = "",
        **args,
    ) -> ShellConnection:
        """Add a widget to the shell.

        If the widget is already in the shell, it may be moved or activated.

        To multiple instances of the same widget in the shell provide a new cid
        with `cid=ShellConnection.to_cid()`.

        Parameters
        ---------
        obj:
            When `obj` is NOT a Widget it is assumed `obj` should be evaluated
            in a python kernel.
            specify additional keyword arguments directly in **args
        area: Area
            The area in the shell where to put obj.
        activate: bool
            Activate the widget once it is added to the shell.
        mode: InsertMode
            The insert mode.
        rank: int
            The rank to apply to the widget.
        ref: ShellConnection
            A connection to a widget in the shell. By default the current active
            widget is used as a reference.
        vpath: str | dict[literal['title':str]]
            **Only relevant for 'evaluate'**
            The 'virtual' path for the app. A new kernel will be created if a session
            doesn't exist with the same path.
            If a dict is provided, a text_dialog will be used to obtain the vpath
            with the hook `vpath_getter`.

            Note:
            The result (payload) of evaluate must be a Widget with a view and
            NOT a ShellConnection.
        options:
            Other options not including

        Basic example
        -------------

        The example evaluates code in a session with path="test". A new kernel is started if a
        session doesn't exist that has a path = vpath.
        ```
        app.shell.add("ipylab.Panel([ipw.HTML('<h1>Test')])", vpath="test")
        ```
        """
        app = await self.app.ready()
        vpath = vpath or app.vpath
        args["options"] = {
            "activate": False,
            "mode": InsertMode(mode),
            "rank": int(rank) if rank else None,
            "ref": f"{pack(ref)}.id" if isinstance(ref, ShellConnection) else None,
        } | (options or {})
        args["area"] = area
        if "asMainArea" not in args:
            args["asMainArea"] = area in [Area.left, Area.main, Area.right, Area.down]
        if isinstance(obj, ShellConnection):
            if "cid" in args and args["cid"] != obj.cid:
                msg = f"The provided {args['cid']=} does not match {obj.cid=}"
                raise RuntimeError(msg)
            args["cid"] = obj.cid
        elif isinstance(obj, Widget):
            if not obj._view_name:  # noqa: SLF001
                msg = f"This widget does not have a view {obj}"
                raise RuntimeError(msg)
            if not args.get("cid") and reversed(self.connections):
                for c in self.connections:
                    if c.widget is obj:
                        args["cid"] = c.cid
                        break
            args["ipy_model"] = obj.model_id
        else:
            args["evaluate"] = pack(obj)
        if isinstance(obj, DOMWidget):
            obj.add_class(app.selector.removeprefix("."))
        if "evaluate" in args and isinstance(vpath, dict):
            val = ipylab.plugin_manager.hook.vpath_getter(app=app, kwgs=vpath)
            while inspect.isawaitable(val):
                val = await val
            vpath = val
        args["vpath"] = vpath

        sc: ShellConnection = await self.operation("addToShell", {"args": args}, transform=Transform.connection)
        sc.add_to_tuple(self, "connections")
        if vpath != app.vpath:
            sc.auto_dispose = False
        if isinstance(obj, Widget):
            sc.widget = obj
            if isinstance(obj, ipylab.Panel):
                sc.add_to_tuple(obj, "connections")
        if activate:
            await sc.activate()
        return sc

    def add_objects_to_ipython_namespace(self, objects: dict, *, reset=False):
        "Load objects into the IPython/console namespace."
        with contextlib.suppress(AttributeError):
            if reset:
                self.comm.kernel.shell.reset()  # type: ignore
            self.comm.kernel.shell.push(objects)  # type: ignore

    async def open_console(
        self,
        *,
        mode=InsertMode.split_bottom,
        activate=True,
        ref: ShellConnection | str = "",
        objects: dict | None = None,
        reset_shell=False,
    ) -> ConsoleConnection:
        """Open/activate a Jupyterlab console for this python kernel shell (path=app.vpath).

        Parameters
        ----------
        ref: ShellConnection | str
            The ShellConnection or `id` of the widget in the shell.
        objects: dict
            Objects to load into the user namespace (shell.user_ns).
            By default `ref` as a ShellConnection is loaded.
        reset_shell:
            Set true to reset the shell (clear the namespace).
        """
        await self.ready()
        app = await self.app.ready()
        ref_ = ref or self.current_widget_id
        if not isinstance(ref_, ShellConnection):
            ref_ = await self.connect_to_widget(ref_)
        objects_ = {"ref": ref_} | (objects or {})
        args = {"path": app.vpath, "insertMode": InsertMode(mode), "activate": activate, "ref": f"{pack(ref_)}.id"}
        tf: TransformType = {"transform": Transform.connection, "cid": ConsoleConnection.to_cid(app.vpath)}
        cc: ConsoleConnection = await app.commands.execute("console:open", args, toObject=["args[ref]"], transform=tf)
        self.console = cc
        cc.add_to_tuple(self, "connections")
        self.add_objects_to_ipython_namespace(objects_, reset=reset_shell)
        return cc

    async def expand_left(self):
        await self.execute_method("expandLeft")

    async def expand_right(self):
        await self.execute_method("expandRight")

    async def collapse_left(self):
        await self.execute_method("collapseLeft")

    async def collapse_right(self):
        await self.execute_method("collapseRight")

    async def connect_to_widget(self, widget_id="", **kwgs: Unpack[IpylabKwgs]) -> ShellConnection:
        "Make a connection to a widget in the shell (see also `get_widget_ids`)."
        kwgs["transform"] = Transform.connection
        return await self.operation("getWidget", {"id": widget_id}, **kwgs)

    async def list_widget_ids(self, **kwgs: Unpack[IpylabKwgs]) -> dict[Area, list[str]]:
        "Get a mapping of Areas to a list of widget ids in that area in the shell."
        return await self.operation("getWidgetIds", **kwgs)
