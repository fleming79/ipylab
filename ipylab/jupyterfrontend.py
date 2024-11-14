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
from traitlets import Bool, Container, Dict, Instance, Unicode, UseEnum, default, observe

import ipylab
import ipylab.hookspecs
from ipylab import Ipylab, ShellConnection, Transform
from ipylab._compat.typing import override
from ipylab.commands import APP_COMMANDS_NAME, CommandPalette, CommandRegistry
from ipylab.common import InsertMode, IpylabKwgs, Obj, to_selector
from ipylab.dialog import Dialog
from ipylab.ipylab import IpylabBase, Readonly
from ipylab.launcher import Launcher
from ipylab.log import IpylabLogFormatter, IpylabLogHandler, LogLevel
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
    logger_level = UseEnum(LogLevel, read_only=True, default_value=LogLevel.warning).tag(sync=True)
    vpath = Unicode(read_only=True).tag(sync=True)
    per_kernel_widget_manager_detected = Bool(read_only=True).tag(sync=True)

    shell = Readonly(Shell)
    dialog = Readonly(Dialog)
    notification = Readonly(NotificationManager)
    commands = Readonly(CommandRegistry, name=APP_COMMANDS_NAME)
    launcher = Readonly(Launcher)
    main_menu = Readonly(MainMenu)
    command_pallet = Readonly(CommandPalette)
    context_menu = Readonly(ContextMenu, sub_attrs=["commands"], commands=lambda app: app.commands)
    sessions = Readonly(SessionManager)

    console = Instance(ShellConnection, allow_none=True, read_only=True)
    logging_handler = Instance(IpylabLogHandler, read_only=True)

    active_namespace = Unicode("", read_only=True, help="name of the current namespace")
    selector = Unicode("", read_only=True, help="Selector class for context menus (css)")

    namespaces: Container[dict[str, LastUpdatedDict]] = Dict(read_only=True)  # type: ignore

    _ipy_shell = get_ipython()
    _ipy_default_namespace: ClassVar = getattr(_ipy_shell, "user_ns", {})

    @classmethod
    @override
    def _single_key(cls, kwgs: dict):  # noqa: ARG003
        return "app"

    def close(self):
        "Cannot close"

    @default("log")
    def _default_log(self):
        log = logging.getLogger("ipylab")
        self.logging_handler.set_as_handler(log)
        return log

    @default("logging_handler")
    def _default_logging_handler(self):
        handler = IpylabLogHandler()
        fmt = "{owner} {obj} {message}"
        handler.setFormatter(IpylabLogFormatter(fmt, style="{"))
        return handler

    @observe("_ready")
    def _app_observe_ready(self, _):
        if self._ready:
            self.set_trait("selector", to_selector(self.vpath))
            ipylab.plugin_manager.hook.autostart._call_history.clear()  # type: ignore  # noqa: SLF001
            ipylab.plugin_manager.hook.autostart.call_historic(
                kwargs={"app": self}, result_callback=self._autostart_callback
            )

    def _autostart_callback(self, result):
        self.ensure_run(result)

    @property
    def repr_info(self):
        return {"vpath": self.vpath}

    @override
    async def ready(self):
        if not self._ready_event._value:  # type: ignore # noqa: SLF001
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
        return await super()._do_operation_for_frontend(operation, payload, buffers)

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

    def _context_open_console(self, ref: ShellConnection, current_widget: ShellConnection):
        "This command is provided for the 'autostart' context menu."
        return self.open_console(objects={"ref": ref, "current_widget": current_widget})

    def open_console(
        self,
        *,
        insertMode=InsertMode.split_bottom,
        namespace_name="",
        activate=True,
        objects: dict | None = None,
        **kwargs: Unpack[IpylabKwgs],
    ) -> Task[ShellConnection]:
        """Open a console and activate the namespace.
        namespace_name: str
            An alternate namespace to load into the console.
        """

        async def _open_console():
            args = {
                "path": self.vpath,
                "insertMode": insertMode,
                "activate": activate,
                "namespace_name": namespace_name,
            }
            kwargs["transform"] = {"transform": Transform.connection}

            # plugins
            plugin_results = ipylab.plugin_manager.hook.opening_console(
                app=self, args=args, objects=objects, kwgs=kwargs
            )
            for result in plugin_results:
                self.ensure_run(result)
            self.activate_namespace(args.pop("namespace_name", ""), objects=objects)

            conn: ShellConnection = await self.commands.execute("console:open", args, **kwargs)
            conn.add_as_trait(self, "console")
            if objects and (ref := objects.get("ref")) and isinstance(ref.widget, ipylab.Panel):
                conn.add_as_trait(ref.widget, "console")
            return conn

        return self.to_task(_open_console(), "Open console")

    def shutdown_kernel(self, vpath: str | None = None):
        "Shutdown the kernel"
        return self.operation("shutdownKernel", {"vpath": vpath})

    def start_iyplab_python_kernel(self, *, restart=False):
        "Start the 'ipylab' Python kernel."
        return self.operation("startIyplabKernel", {"restart": restart})

    def evaluate(
        self,
        evaluate: dict[str, str | inspect._SourceObjectType] | str,
        *,
        vpath="",
        name="",
        namespace_name="",
        **kwargs: Unpack[IpylabKwgs],
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
        kwgs = {"evaluate": evaluate, "vpath": vpath, "name": name, "namespace_name": namespace_name}
        return self.operation("evaluate", kwgs, **kwargs)

    def get_namespace(self, name="", objects: dict | None = None):
        "Get the 'globals' namespace stored for name."
        if self._ipy_shell:
            if "" not in self.namespaces:
                self.namespaces[""] = LastUpdatedDict(self._ipy_shell.user_ns)
            if self.active_namespace == name:
                self.namespaces.update(self._ipy_shell.user_ns)
        if name not in self.namespaces:
            self.namespaces[name] = LastUpdatedDict(self._ipy_default_namespace)
        objects = {"ipylab": ipylab, "ipywidgets": ipywidgets, "ipw": ipywidgets, "app": self} | (objects or {})
        ipylab.plugin_manager.hook.namespace_objects(objects=objects, namespace_name=name, app=self)
        self.namespaces[name].update(objects)
        return self.namespaces[name]

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
        self.namespaces.pop(name, None)
        if activate:
            self.activate_namespace(name, objects)
