# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import functools
import inspect
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Unpack

import ipywidgets
from IPython.core.getipython import get_ipython
from ipywidgets import Widget, register
from traitlets import Bool, Container, Dict, Instance, Tuple, Unicode, UseEnum, default, observe

import ipylab
import ipylab.hookspecs
from ipylab import Ipylab, ShellConnection, Transform
from ipylab._compat.typing import override
from ipylab.commands import CommandPalette, CommandRegistry
from ipylab.common import InsertMode, IpylabKwgs, Obj, pack
from ipylab.dialog import Dialog
from ipylab.ipylab import IpylabBase
from ipylab.launcher import Launcher
from ipylab.log import IpylabLogHandler, LogLevel
from ipylab.menu import ContextMenu, MainMenu
from ipylab.notification import NotificationManager
from ipylab.sessions import SessionManager
from ipylab.shell import Shell

if TYPE_CHECKING:
    from asyncio import Task
    from typing import ClassVar


class LastUpdatedDict(OrderedDict):
    "Store items in the order the keys were last added"

    # ref: https://docs.python.org/3/library/collections.html#ordereddict-examples-and-recipes

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)


@register
class App(Ipylab):
    "A connection to the 'app' in the frontend. A singleton (per kernel) not to be subclassed."

    SINGLE = True

    _model_name = Unicode("JupyterFrontEndModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app").tag(sync=True)
    version = Unicode(read_only=True).tag(sync=True)
    current_widget_id = Unicode(read_only=True).tag(sync=True)
    logger_level = UseEnum(LogLevel, read_only=True, default_value=LogLevel.warning).tag(sync=True)
    current_session = Dict(read_only=True).tag(sync=True)
    all_sessions = Tuple(read_only=True).tag(sync=True)
    vpath = Unicode(read_only=True).tag(sync=True)
    per_kernel_widget_manager_detected = Bool(read_only=True).tag(sync=True)

    shell = Instance(Shell, (), read_only=True)
    dialog = Instance(Dialog, (), read_only=True)
    commands = Instance(CommandRegistry, (), read_only=True)
    command_pallet = Instance(CommandPalette, (), read_only=True)
    launcher = Instance(Launcher, (), read_only=True)
    session_manager = Instance(SessionManager, (), read_only=True)
    main_menu = Instance(MainMenu, (), read_only=True)
    context_menu = Instance(ContextMenu, (), read_only=True)
    notification = Instance(NotificationManager, (), read_only=True)
    console = Instance(ShellConnection, allow_none=True, read_only=True)
    log_handler = Instance(logging.Handler, allow_none=True, read_only=True)

    active_namespace = Unicode("", read_only=True, help="name of the current namespace")

    namespace_names: Container[tuple[str, ...]] = Tuple(read_only=True).tag(sync=True)
    _namespaces: Container[dict[str, LastUpdatedDict]] = Dict(read_only=True)  # type: ignore

    _ipy_shell = get_ipython()
    _ipy_default_namespace: ClassVar = getattr(_ipy_shell, "user_ns", {})

    def __init_subclass__(cls, **kwargs) -> None:
        msg = "Subclassing the `App` class is not allowed!"
        raise RuntimeError(msg)

    def __init__(self, **kwgs):
        if self._async_widget_base_init_complete:
            return
        if vpath := kwgs.pop("vpath", None):
            self.set_trait("vpath", vpath)
        super().__init__(**kwgs)

    def close(self):
        "Cannot close"

    @default("log")
    def _default_log(self):
        logger = logging.getLogger("ipylab")
        if isinstance(self.log_handler, logging.Handler):
            logger.addHandler(self.log_handler)
        return logger

    @default("log_handler")
    def _default_log_handler(self):
        handler = IpylabLogHandler(self)
        fmt = "{name}:{message}"
        handler.setFormatter(logging.Formatter(fmt, style="{"))
        return handler

    @observe("_ready")
    def _app_observe_ready(self, _):
        if self._ready:
            self.hook.autostart._call_history.clear()  # type: ignore  # noqa: SLF001
            self.hook.autostart.call_historic(kwargs={"app": self}, result_callback=self._autostart_callback)

    def _autostart_callback(self, result):
        self.hook.ensure_run(obj=self, aw=result)

    @property
    def repr_info(self):
        return {"vpath": self.vpath}

    @override
    async def ready(self):
        await self._ready_event.wait()

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        match operation:
            case "evaluate":
                return await self._evaluate(payload, buffers)
            case "shell_eval":
                result = await self._evaluate(payload, buffers)
                widget = result.get("payload")
                if not isinstance(widget, Widget):
                    msg = f"Expected an Widget but got {type(widget)}"
                    raise TypeError(msg)
                result["payload"] = await self.shell.add(widget, **payload)
                return result
            case "open_console":
                async with ShellConnection(payload["cid"]) as ref:
                    return await self._open_console(
                        args=payload.get("args") or {},
                        namespace_name=payload.get("namespace_name", ""),
                        objects={"widget": ref.widget, "ref": ref},
                    )
        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def _open_console(self, args: dict, objects: dict, namespace_name: str, **kwgs: Unpack[IpylabKwgs]):
        args = {"path": self.vpath, "insertMode": InsertMode.split_bottom} | args
        kwgs["transform"] = {"transform": Transform.connection}
        kwgs["namespace_name"] = namespace_name  # type: ignore

        # plugins
        plugin_results = self.hook.opening_console(app=self, args=args, objects=objects, kwgs=kwgs)
        for pr in plugin_results:
            if inspect.isawaitable(pr):
                await pr

        if "ref" not in args and (ref := objects.get("ref")):
            args["ref"] = f"{pack(ref)}.id"
            kwgs["toObject"] = [*kwgs.pop("toObject", []), "args.ref"]

        if (namespace_name := kwgs.pop("namespace_name", "")) is not None:  # type: ignore
            self.activate_namespace(namespace_name, objects=objects)

        conn: ShellConnection = await self.commands.execute("console:open", args, **kwgs)
        conn.add_as_trait(self, "console")
        if isinstance((widget := objects.get("widget")), ipylab.Panel):
            conn.add_as_trait(widget, "console")
        return conn

    async def _evaluate(self, options: dict, buffers: list):
        """Evaluate code corresponding to a call from 'evaluate'.

        A call to this method should originate from either:
         1. An `evaluate` method call from a subclass of `Ipylab`.
         2. A direct call in the frontend at jfem.evaluate.

        """
        namespace_name = options.get("namespace_name", "")
        glbls = self.get_namespace(namespace_name, options | {"buffers": buffers})
        evaluate = options.get("evaluate", {})
        if isinstance(evaluate, str):
            evaluate = {"payload": evaluate}
        for name, expression in evaluate.items():
            try:
                result = eval(expression, glbls, glbls)  # noqa: S307
            except SyntaxError:
                exec(expression, glbls, glbls)  # noqa: S102
                result = next(reversed(glbls.values()))
            while callable(result) or inspect.isawaitable(result):
                if callable(result):
                    pnames = set(glbls).intersection(inspect.signature(result).parameters)
                    kwgs = {name: glbls[name] for name in pnames}
                    glbls[name] = functools.partial(result, **kwgs)
                    result = eval(f"{name}()", glbls)  # type: ignore # noqa: S307
                if inspect.isawaitable(result):
                    result = await result
            glbls[name] = result
        buffers = glbls.pop("buffers", [])
        if namespace_name == self.active_namespace:
            self.activate_namespace(namespace_name)
        else:
            self.get_namespace(namespace_name, glbls)
        return {"payload": glbls.get("payload"), "buffers": buffers}

    def open_console(
        self,
        *,
        insertMode=InsertMode.split_bottom,
        namespace_name="",
        activate=True,
        objects: dict | None = None,
        **kwgs: Unpack[IpylabKwgs],
    ) -> Task[ShellConnection]:
        """Open a console and activate the namespace.
        namespace_name: str
            An alternate namespace to load into the console.
        """
        args = {"activate": activate, "insertMode": InsertMode(insertMode)}
        coro = self._open_console(args, objects=objects or {}, namespace_name=namespace_name, **kwgs)
        return self.to_task(coro, "Open console")

    def toggle_log_console(self) -> Task[ShellConnection]:
        # How can we check if the log console is open?
        return self.commands.execute("logconsole:open", {"source": self.vpath})

    def shutdown_kernel(self, vpath: str | None = None):
        "Shutdown the kernel"
        return self.operation("shutdownKernel", vpath=vpath)

    def start_iyplab_python_kernel(self, *, restart=False):
        "Start the 'ipylab' Python kernel."
        return self.operation("startIyplabKernel", restart=restart)

    def evaluate(
        self,
        evaluate: dict[str, str | inspect._SourceObjectType] | str,
        *,
        vpath="",
        name="",
        namespace_name="",
        **kwgs: Unpack[IpylabKwgs],
    ):
        """Evaluate code in a Python kernel.

        If `vpath` isn't provided a session matching the path will be used, possibly prompting for a kernel.

        evaluate:
            An expression to evaluate or execute.

            The evaluation expression will also be called and or awaited until the returned symbol is no
            longer callable or awaitable.
            String:
                If it is string it will be evaluated and returned.
            Dict: Advanced usage:
            A dictionary of `symbol name` to `expression` mappings to be evaluated in the kernel.
            Each expression is evaluated in turn adding the symbol to the namespace.

            Expression can be a the name of a function or class. In which case it will be evaluated
            using parameter names matching the signature of the function or class.

            ref: https://docs.python.org/3/library/functions.html#eval

            Once evaluation is complete, the symbols named `payload` and `buffers` will be returned.
        vpath:
            The path used for the kernel session context.
        globals:
            The globals namespace includes the follow symbols:
            * ipylab
            * ipywidgets
            * ipw (ipywidgets)
        """
        return self.app.operation(
            "evaluate", evaluate=evaluate, vpath=vpath, name=name, namespace_name=namespace_name, **kwgs
        )

    def get_namespace(self, name="", objects: dict | None = None):
        "Get the 'globals' namespace stored for name."
        if self._ipy_shell:
            if "" not in self._namespaces:
                self._namespaces[""] = LastUpdatedDict(self._ipy_shell.user_ns)
            if self.active_namespace == name:
                self._namespaces.update(self._ipy_shell.user_ns)
        if name not in self._namespaces:
            self._namespaces[name] = LastUpdatedDict(self._ipy_default_namespace)
        objects = {"ipylab": ipylab, "ipywidgets": ipywidgets, "ipw": ipywidgets, "app": self} | (objects or {})
        self.hook.namespace_objects(objects=objects, namespace_name=name, app=self)
        self._namespaces[name].update(objects)
        return self._namespaces[name]

    def activate_namespace(self, name="", objects: dict | None = None):
        "Sets the ipython/console namespace."
        if not self._ipy_shell:
            msg = "Ipython shell is not loaded!"
            raise RuntimeError(msg)
        ns = self.get_namespace(name, objects)
        self._ipy_shell.reset()
        self._ipy_shell.push(ns)
        self.set_trait("active_namespace", name)

    def reset_namespace(self, name: str, *, activate=True, objects: dict | None = None):
        "Reset the namespace to default. If activate is False it won't be created."
        self._namespaces.pop(name, None)
        if activate:
            self.activate_namespace(name, objects)
