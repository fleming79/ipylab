# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
from typing import TYPE_CHECKING, Any, Unpack

from ipywidgets import Widget, register
from traitlets import Bool, Container, Dict, Instance, Unicode, UseEnum, default, observe

import ipylab
from ipylab import Ipylab
from ipylab._compat.typing import override
from ipylab.commands import APP_COMMANDS_NAME, CommandPalette, CommandRegistry
from ipylab.common import IpylabKwgs, LastUpdatedDict, Obj, Readonly, to_selector
from ipylab.dialog import Dialog
from ipylab.ipylab import IpylabBase
from ipylab.launcher import Launcher
from ipylab.log import IpylabLogFormatter, IpylabLogHandler, LogLevel
from ipylab.menu import ContextMenu, MainMenu
from ipylab.notification import NotificationManager
from ipylab.sessions import SessionManager
from ipylab.shell import Shell

if TYPE_CHECKING:
    from typing import ClassVar


@register
class App(Ipylab):
    "A connection to the 'app' in the frontend. A singleton (per kernel) not to be subclassed."

    SINGLE = True
    DEFAULT_COMMANDS: ClassVar = {"Open console", "Show log viewer"}
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
    context_menu = Readonly(ContextMenu, commands=lambda app: app.commands, dynamic=["commands"])
    sessions = Readonly(SessionManager)

    logging_handler: Instance[IpylabLogHandler | None] = Instance(IpylabLogHandler, allow_none=True)  # type: ignore
    log_level = UseEnum(LogLevel, LogLevel.ERROR)

    namespaces: Container[dict[str, LastUpdatedDict]] = Dict(read_only=True)  # type: ignore

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
        handler.setFormatter(IpylabLogFormatter(fmt=fmt, style="{", datefmt="%H:%M:%S"))
        return handler

    @observe("_ready", "log_level")
    def _app_observe_ready(self, change):
        if change["name"] == "_ready" and self._ready:
            assert self.vpath, "Vpath should always before '_ready'."  # noqa: S101
            self._selector = to_selector(self.vpath)
            ipylab.plugin_manager.hook.autostart._call_history.clear()  # type: ignore  # noqa: SLF001
            try:
                ipylab.plugin_manager.hook.autostart.call_historic(
                    kwargs={"app": self}, result_callback=self._autostart_callback
                )
            except Exception:
                self.log.exception("Error with autostart")
        if self.logging_handler:
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
        try:
            if not self._ready_event._value:  # type: ignore # noqa: SLF001
                await self._ready_event.wait()
        except RuntimeError:
            if self.comm.__class__.__name__ == "DummyComm":
                self.log.info("No frontend")
                await asyncio.sleep(1e9)
            raise

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
         1. An `evaluate` method call from a subclass of `Ipylab` from kernel via
            `jfem.evaluate` in the frontend.
         2. A call in the frontend to `jfem.evaluate`.
        """
        evaluate = options["evaluate"]
        if isinstance(evaluate, str):
            evaluate = {"payload": evaluate}
        namespace_id = options.get("namespace_id", "")
        ns = self.get_namespace(namespace_id, buffers=buffers)
        for name, expression in evaluate.items():
            try:
                result = eval(expression, ns)  # noqa: S307
            except SyntaxError:
                exec(expression, ns)  # noqa: S102
                result = next(reversed(ns.values()))  # Requires: LastUpdatedDict
            while callable(result) or inspect.isawaitable(result):
                if callable(result):
                    kwgs = {}
                    for p in inspect.signature(result).parameters:
                        if p in options:
                            kwgs[p] = options[p]
                        if p in ns:
                            kwgs[p] = ns[p]
                    # We use a partial so that we can evaluate with the same namespace.
                    ns["_partial_call"] = functools.partial(result, **kwgs)
                    result = eval("_partial_call()", ns)  # type: ignore # noqa: S307
                    ns.pop("_partial_call")
                while inspect.isawaitable(result):
                    result = await result
            ns[name] = result
        buffers = ns.pop("buffers", [])
        payload = ns.pop("payload", None)
        if payload is not None:
            ns["_call_count"] = n = ns.get("_call_count", 0) + 1
            ns[f"payload_{n}"] = payload
        if namespace_id == "":
            self.shell.add_objects_to_ipython_namespace(ns)
        return {"payload": payload, "buffers": buffers}

    def shutdown_kernel(self, vpath: str | None = None):
        "Shutdown the kernel"
        return self.operation("shutdownKernel", {"vpath": vpath})

    def start_iyplab_python_kernel(self, *, restart=False):
        "Start the 'ipylab' Python kernel."
        return self.operation("startIyplabKernel", {"restart": restart})

    def get_namespace(self, namespace_id="", **objects) -> LastUpdatedDict:
        """Get the namespace corresponding to namespace_id.
        The namespace is a dictionary that maintains the order by which items are added.

        Default oubjects are added to the namespace via the plugin hook `default_namespace_objects`.

        Note:
            To remove a namespace call `ipylab.app.namespaces.pop(<namespace_id>)`.

        The default namespace ("") will also load objects from `shell.user_ns`.

        Parameters
        ----------
            objects:
                Additional objects to add to the namespace.
        """
        ns = self.namespaces.get(namespace_id)
        if ns is None:
            self.namespaces[namespace_id] = ns = LastUpdatedDict()
            for objs in ipylab.plugin_manager.hook.default_namespace_objects(namespace_id=namespace_id, app=self):
                ns.update(objs)
        if objects:
            ns.update(objects)
        if namespace_id == "":
            with contextlib.suppress(AttributeError):
                ns.update(self.comm.kernel.shell.user_ns)  # type: ignore
        return ns

    def evaluate(
        self,
        evaluate: dict[str, str | inspect._SourceObjectType] | str,
        *,
        vpath="",
        namespace_id="",
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
        namespace_id:
            The namespace where to perform evaluation.
            The default namespace will also update the shell.user_ns after successful evaluation.
        """
        kwgs = {"evaluate": evaluate, "vpath": vpath, "namespace_id": namespace_id}
        return self.operation("evaluate", kwgs, **kwargs)


JupyterFrontEnd = App
