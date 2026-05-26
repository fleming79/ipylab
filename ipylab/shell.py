# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Literal, Unpack

from aiologic import BinarySemaphore
from async_kernel.common import Fixed
from ipywidgets import DOMWidget, TypedTuple, Widget
from traitlets import Container, Instance, Unicode

import ipylab
from ipylab.common import Area, InsertMode, IpylabKwgs, Obj, Singular, Transform, TransformType, W_co, pack
from ipylab.connection import ShellConnection
from ipylab.ipylab import Ipylab, IpylabBase
from ipylab.log_viewer import LogViewer

if TYPE_CHECKING:
    from types import FunctionType
    from typing import Literal


__all__ = ["ConsoleConnection", "Shell"]


class ConsoleConnection(ShellConnection):
    "A connection intended for a JupyterConsole."

    subshell_id = Unicode(None, allow_none=True)

    async def inject(self, code: str, **metadata) -> None:
        """Inject and execute code in the console."""
        # Specify a task in case this is called from an execute request from the same shell.
        metadata["tags"] = [*metadata.get("tags", ()), "task"]
        await self.execute_method("console.inject", (code, metadata))


class Shell(Singular, Ipylab):
    """Provides access to the shell."""

    _model_name = Unicode("ShellModel", help="Name of the model.", read_only=True).tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app.shell").tag(sync=True)
    current_widget_id = Unicode(read_only=True).tag(sync=True)

    _lock = Fixed(BinarySemaphore)

    log_viewer = Fixed(LogViewer)

    connections: Container[tuple[ShellConnection, ...]] = TypedTuple(trait=Instance(ShellConnection))
    consoles: Container[tuple[ConsoleConnection, ...]] = TypedTuple(trait=Instance(ConsoleConnection))

    async def add(
        self,
        obj: W_co | FunctionType,
        *,
        area: Area = Area.main,
        activate: bool = True,
        mode: InsertMode = InsertMode.tab_after,
        rank: int | None = None,
        ref: ShellConnection | None = None,
        options: dict | None = None,
        vpath: str | dict[Literal["title"], str] = "",
        preferred_kernel: Literal["async", "python3"] | str = "async",  # noqa: PYI051
        **args,
    ) -> ShellConnection[W_co]:
        """
        Add a widget to the shell.

        If the widget is already in the shell, it may be moved or activated.

        To force multiple instances of the same widget in the shell provide a new `connection_id`
        with `connection_id=ShellConnection.to_id()`.

        Args:
            obj: When `obj` is NOT a Widget it is assumed `obj` should be evaluated in a python kernel. Specify additional keyword arguments directly in **args
            area: The area in the shell where to put obj.
            activate: Activate the widget once it is added to the shell.
            mode: The insert mode.
            rank: The rank to apply to the widget.
            ref: A connection to a widget in the shell. By default the current active widget is used as a reference.
            vpath:
                **Only relevant for 'evaluate'**

                The 'virtual' path for the app. A new kernel will be created if a session
                doesn't exist with the same path. If a dict is provided, a text_dialog will
                be used to obtain the vpath with the hook `vpath_getter`.
                Note:
                    The result (payload) of evaluate must be a Widget with a view and NOT a ShellConnection.
            preferred_kernel:
                The name of the kernel to use if a new kernel is started.
            options:
                Other options not including

        Basic example:

            This example evaluates code in a session with vpath="test".

            ```python
            app.shell.add("ipylab.Panel([ipw.HTML('<h1>Test')])", vpath="test")
            ```
        """
        await self.wait_ready()
        vpath = vpath or self.app.vpath
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
            if "connection_id" in args and args["connection_id"] != obj.connection_id:
                msg = f"The provided {args['connection_id']=} does not match {obj.connection_id=}"
                raise RuntimeError(msg)
            args["connection_id"] = obj.connection_id
        elif isinstance(obj, Widget):
            if not obj._view_name:
                msg = f"This widget does not have a view {obj}"
                raise RuntimeError(msg)
            if not args.get("connection_id") and self.connections:
                for c in reversed(self.connections):
                    if c.widget is obj and not c.closed:
                        args["connection_id"] = c.connection_id
                        break
            args["ipy_model"] = obj.model_id
        else:
            args["evaluate"] = pack(obj)
        if isinstance(obj, DOMWidget):
            obj.add_class(self.app.selector.removeprefix("."))
        if "evaluate" in args and isinstance(vpath, dict):
            val = ipylab.plugin_manager.hook.vpath_getter(app=self.app, kwgs=vpath)
            if inspect.iscoroutine(val):
                val = await val
            vpath = val
        args["vpath"] = vpath
        args["preferredKernel"] = preferred_kernel
        sc: ShellConnection = await self.operation(
            "addToShell",
            {"args": args},
            transform=Transform.connection,
        )
        sc.add_to_tuple(self, "connections")
        if vpath != self.app.vpath:
            sc.auto_dispose = False
        if isinstance(obj, Widget):
            sc.widget = obj
            if isinstance(obj, ipylab.Panel):
                sc.add_to_tuple(obj, "connections")
        if activate:
            await sc.activate()
        return sc

    async def open_console(
        self,
        *,
        ref: ShellConnection | str = "",
        objects: dict | None = None,
        subshell_id: str | None = None,
        activate=True,
        mode=InsertMode.split_bottom,
        **args,
    ) -> ConsoleConnection:
        """
        Open/activate a Jupyterlab console for this python kernel shell (path=app.vpath).

        Args:
            mode: The `InsertMode`.
            activate: If the console widget should be activated in the frontend.
            ref: The ShellConnection or `id` of the widget in the shell to set as `ref` in the namespace.
            objects: Objects to load into the user namespace (shell.user_ns). By default `ref` as a `ShellConnection` is loaded.
        """
        await self.wait_ready()
        app = await self.app.wait_ready()
        if subshell_id:
            # Validate the subshell_id.
            self.app.kernel.get_shell(subshell_id)
        with self._lock:
            ref_ = ref or self.current_widget_id
            if not isinstance(ref_, ShellConnection):
                ref_ = await self.connect_to_widget(ref_)
                ref_.auto_dispose = False
            objects_ = {"ref": ref_} | (objects or {})
            if cc_ := next((c for c in self.consoles if c.subshell_id == subshell_id), None):
                cc = cc_
            else:
                args = args | {
                    "path": app.vpath,
                    "insertMode": InsertMode(mode),
                    "activate": False,
                    "ref": f"{pack(ref_)}.id",
                }
                connection_id = ConsoleConnection.to_id(app.vpath, f"{subshell_id=!s}")
                tf: TransformType = {"transform": Transform.connection, "connection_id": connection_id}
                cc: ConsoleConnection = await app.commands.execute(
                    "console:create", args, toObject=["args[ref]"], transform=tf
                )
                cc.add_to_tuple(self, "consoles")
                cc.add_to_tuple(self, "connections")
                await cc.get_property("sessionContext.ready")
                await cc.set_property("sessionContext.session.kernel.subshellId", subshell_id)
                cc.subshell_id = subshell_id
            self.app.add_objects_to_user_ns(subshell_id, **objects_)
        if activate:
            await cc.activate()
        return cc

    async def expand_left(self) -> None:
        await self.execute_method("expandLeft")

    async def expand_right(self) -> None:
        await self.execute_method("expandRight")

    async def collapse_left(self) -> None:
        await self.execute_method("collapseLeft")

    async def collapse_right(self) -> None:
        await self.execute_method("collapseRight")

    async def connect_to_widget(self, widget_id="", **kwgs: Unpack[IpylabKwgs]) -> ShellConnection:
        "Make a connection to a widget in the shell (see also `get_widget_ids`)."
        kwgs["transform"] = Transform.connection
        return await self.operation("getWidget", {"id": widget_id}, **kwgs)

    async def list_widget_ids(self, **kwgs: Unpack[IpylabKwgs]) -> dict[Area, list[str]]:
        "Get a mapping of Areas to a list of widget ids in that area in the shell."
        return await self.operation("getWidgetIds", **kwgs)
