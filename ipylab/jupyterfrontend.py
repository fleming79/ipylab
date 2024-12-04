# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import functools
import inspect
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Literal, Unpack

from IPython.core.getipython import get_ipython
from ipywidgets import Widget, register
from traitlets import Bool, Container, Dict, Instance, Unicode, UseEnum, default, observe

import ipylab
import ipylab.hookspecs
from ipylab import Ipylab, ShellConnection, Transform, log
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
from ipylab.widgets import Panel

if TYPE_CHECKING:
    from asyncio import Task
    from typing import ClassVar

    from ipylab.log_viewer import LogViewer


class LastUpdatedDict(OrderedDict):
    """Store items in the order the keys were last added.

    mode: Literal["first", "last"]
        The end to shift the last added key."""

    # ref: https://docs.python.org/3/library/collections.html#ordereddict-examples-and-recipes
    _updating = False
    _last = True

    def __init__(self, *args, mode: Literal["first", "last"] = "last", **kwargs):
        self._last = mode == "last"
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if not self._updating:
            self.move_to_end(key, self._last)

    @override
    def update(self, m, **kwargs):
        self._updating = True
        try:
            super().update(m, **kwargs)
        finally:
            self._updating = False


@register
class App(Ipylab):
    "A connection to the 'app' in the frontend. A singleton (per kernel) not to be subclassed."

    SINGLE = True

    _model_name = Unicode("JupyterFrontEndModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app").tag(sync=True)
    version = Unicode(read_only=True).tag(sync=True)
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
    log_viewer: Instance[LogViewer] = Instance(Panel, read_only=True)  # type: ignore
    log_level = UseEnum(LogLevel, LogLevel.ERROR)

    active_namespace = Unicode("", read_only=True, help="name of the current namespace")

    namespaces: Container[dict[str, LastUpdatedDict]] = Dict(read_only=True)  # type: ignore

    _ipy_shell = get_ipython()
    _hidden: ClassVar = {"_ih", "_oh", "_dh", "In", "Out", "get_ipython", "exit", "quit", "open"}

    @classmethod
    @override
    def _single_key(cls, kwgs: dict):  # noqa: ARG003
        return "app"

    def close(self):
        "Cannot close"

    @default("logging_handler")
    def _default_logging_handler(self):
        fmt = "{color}{level_symbol} {asctime}.{msecs:0<3.0f} {name} {owner_rep}:{reset} {message}\n"
        handler = IpylabLogHandler(self.log_level)
        handler.setFormatter(IpylabLogFormatter(fmt=fmt, style="{", datefmt="%H:%M:%S", colors=log.COLORS))
        return handler

    @default("log_viewer")
    def _default_log_viewer(self):
        return ipylab.plugin_manager.hook.get_log_viewer(app=self, handler=self.logging_handler)

    @observe("_ready", "log_level")
    def _app_observe_ready(self, change):
        if change["name"] == "_ready" and self._ready:
            assert self.vpath, "Vpath should always before '_ready'."  # noqa: S101
            self._selector = to_selector(self.vpath)
            ipylab.plugin_manager.hook.autostart._call_history.clear()  # type: ignore  # noqa: SLF001
            ipylab.plugin_manager.hook.autostart.call_historic(
                kwargs={"app": self}, result_callback=self._autostart_callback
            )
        self.logging_handler.setLevel(self.log_level)

    def _autostart_callback(self, result):
        self.ensure_run(result)

    @property
    def repr_info(self):
        return {"vpath": self.vpath}

    @property
    def repr_log(self):
        "A representation to use when logging"
        return self.__class__.__name__

    @property
    def selector(self):
        # Calling this before `_ready` is set will raise an attribute error.
        return self._selector

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
        return {"payload": glbls.get("payload"), "buffers": buffers}

    def _context_open_console(
        self,
        ref: ShellConnection | None = None,
        current_widget: ShellConnection | None = None,
        namespace_name="",
    ):
        "This command is provided for the 'autostart' context menu."
        return self.open_console(objects={"ref": ref, "current_widget": current_widget}, namespace_name=namespace_name)

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
            namespace_name_ = args.pop("namespace_name", "")
            conn: ShellConnection = await self.commands.execute("console:open", args, **kwargs)
            conn.add_as_trait(self, "console")
            if objects and (ref := objects.get("ref")) and isinstance(ref.widget, ipylab.Panel):
                conn.add_as_trait(ref.widget, "console")
            self.activate_namespace(namespace_name_, objects=objects)
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
            The path of kernel session where to perform the evaluation.
        globals:
            The globals namespace includes the follow symbols:
            * ipylab
            * ipywidgets
            * ipw (ipywidgets)
        """
        kwgs = {"evaluate": evaluate, "vpath": vpath, "namespace_name": namespace_name}
        return self.operation("evaluate", kwgs, **kwargs)

    def get_namespace(self, name="", objects: dict | None = None):
        "Get the 'globals' namespace stored for name."
        sh = self._ipy_shell
        if sh and "" not in self.namespaces:
            self._init_namespace(name, sh.user_ns)
        if name not in self.namespaces:
            self._init_namespace(name, {})
        ns = self.namespaces[name]
        for objs in ipylab.plugin_manager.hook.default_namespace_objects(namespace_name=name, app=self):
            ns.update(objs)
        if objects:
            ns.update(objects)
        if sh and name == self.activate_namespace:
            ns.update(sh.user_ns)
        return ns

    def _init_namespace(self, name: str, objs: dict):
        self.namespaces[name] = LastUpdatedDict(objs)

    def activate_namespace(self, name="", objects: dict | None = None):
        "Sets the ipython/console namespace."
        ns = self.get_namespace(name, objects)
        if self._ipy_shell:
            self._ipy_shell.reset()
            self._ipy_shell.push({k: v for k, v in ns.items() if k not in self._hidden})
        self.set_trait("active_namespace", name)
        return ns

    def reset_namespace(self, name: str, *, activate=True, objects: dict | None = None):
        "Reset the namespace to default. If activate is False it won't be created."
        self.namespaces.pop(name, None)
        if activate:
            self.activate_namespace(name, objects)


JupyterFrontEnd = App
