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
from ipylab.common import Fixed, IpylabKwgs, Obj, TaskHookType
from ipylab.ipylab import IpylabBase
from ipylab.log_viewer import LogViewer

if TYPE_CHECKING:
    from asyncio import Task
    from typing import Literal

    from ipylab.common import TaskHooks


__all__ = ["Shell", "ConsoleConnection"]


class ConsoleConnection(ShellConnection):
    "A connection intended for a JupyterConsole"

    # TODO: add methods


class Shell(Ipylab):
    """Provides access to the shell."""

    SINGLE = True

    _model_name = Unicode("ShellModel", help="Name of the model.", read_only=True).tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app.shell").tag(sync=True)
    current_widget_id = Unicode(read_only=True).tag(sync=True)

    log_viewer = Fixed(LogViewer)

    connections: Container[tuple[ShellConnection, ...]] = TypedTuple(trait=Instance(ShellConnection))
    console: Instance[ConsoleConnection | None] = Instance(ConsoleConnection, default_value=None, allow_none=True)  # type: ignore

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
        vpath: str | dict[Literal["title"], str] = "",
        hooks: TaskHookType = None,
        **args,
    ) -> Task[ShellConnection]:
        """Add a widget to the shell.

        If the widget is already in the shell, it may be moved or activated.

        To multiple instances of the same widget in the shell provide a new cid
        with `cid=ShellConnection.to_cid()`.

        Parameters
        ---------
        obj:
            When `obj` is NOT a Widget it is assumed `obj` should be evaluated
            in a python kernel.
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
        hooks_: TaskHooks = {"add_to_tuple_fwd": [(self, "connections")]}
        args["options"] = {
            "activate": activate,
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
            hooks_["trait_add_fwd"] = [("widget", obj)]
            if isinstance(obj, ipylab.Panel):
                hooks_["add_to_tuple_fwd"].append((obj, "connections"))
            args["ipy_model"] = obj.model_id
        else:
            args["evaluate"] = pack(obj)

        async def add_to_shell() -> ShellConnection:
            vpath_ = await ipylab.app.vpath()
            if isinstance(obj, DOMWidget):
                obj.add_class((await ipylab.app.selector()).removeprefix("."))
            if "evaluate" in args:
                if isinstance(vpath, dict):
                    result = ipylab.plugin_manager.hook.vpath_getter(app=ipylab.app, kwgs=vpath)
                    while inspect.isawaitable(result):
                        result = await result
                    args["vpath"] = result
                else:
                    args["vpath"] = vpath or vpath_
                if args["vpath"] != vpath_:
                    hooks_["trait_add_fwd"] = [("auto_dispose", False)]
            else:
                args["vpath"] = vpath_

            return await self.operation("addToShell", {"args": args}, transform=Transform.connection, hooks=hooks_)

        return self.to_task(add_to_shell(), "Add to shell", hooks=hooks)

    def add_objects_to_ipython_namespace(self, objects: dict, *, reset=False):
        "Load objects into the IPython/console namespace."
        with contextlib.suppress(AttributeError):
            if reset:
                self.comm.kernel.shell.reset()  # type: ignore
            self.comm.kernel.shell.push(objects)  # type: ignore

    def open_console(
        self,
        *,
        mode=InsertMode.split_bottom,
        activate=True,
        ref: ShellConnection | str = "",
        objects: dict | None = None,
        reset_shell=False,
        hooks: TaskHookType = None,
    ) -> Task[ConsoleConnection]:
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

        async def open_console():
            ref_ = ref or self.current_widget_id
            if not isinstance(ref_, ShellConnection):
                ref_ = await self.connect_to_widget(ref_)
            objects_ = {"ref": ref_} | (objects or {})
            vpath_ = await ipylab.app.vpath()
            args = {
                "path": vpath_,
                "insertMode": InsertMode(mode),
                "activate": activate,
                "ref": f"{pack(ref_)}.id",
            }
            kwgs = IpylabKwgs(
                transform={"transform": Transform.connection, "cid": ConsoleConnection.to_cid(vpath_)},
                toObject=["args[ref]"],
                hooks={
                    "trait_add_rev": [(self, "console")],
                    "add_to_tuple_fwd": [(self, "connections")],
                    "callbacks": [lambda _: self.add_objects_to_ipython_namespace(objects_, reset=reset_shell)],
                },
            )
            return await ipylab.app.commands.execute("console:open", args, **kwgs)

        return self.to_task(open_console(), "Open console", hooks=hooks)

    def expand_left(self):
        return self.execute_method("expandLeft")

    def expand_right(self):
        return self.execute_method("expandRight")

    def collapse_left(self):
        return self.execute_method("collapseLeft")

    def collapse_right(self):
        return self.execute_method("collapseRight")

    def connect_to_widget(self, widget_id="", **kwgs: Unpack[IpylabKwgs]) -> Task[ShellConnection]:
        "Make a connection to a widget in the shell (see also `get_widget_ids`)."
        kwgs["transform"] = Transform.connection
        return self.operation("getWidget", {"id": widget_id}, **kwgs)

    def list_widget_ids(self, **kwgs: Unpack[IpylabKwgs]) -> Task[dict[Area, list[str]]]:
        "Get a mapping of Areas to a list of widget ids in that area in the shell."
        return self.operation("getWidgetIds", **kwgs)
