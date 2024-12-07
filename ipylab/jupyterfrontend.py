# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import functools
import inspect
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Literal, Unpack

from IPython.core import completer as IPC  # noqa: N812
from ipywidgets import TypedTuple, Widget, register
from traitlets import Bool, Container, Dict, Instance, Unicode, UseEnum, default, observe

import ipylab
import ipylab.hookspecs
from ipylab import Ipylab
from ipylab._compat.typing import override
from ipylab.commands import APP_COMMANDS_NAME, CommandPalette, CommandRegistry
from ipylab.common import InsertMode, IpylabKwgs, Obj, Transform, to_selector
from ipylab.connection import ShellConnection
from ipylab.dialog import Dialog
from ipylab.ipylab import IpylabBase, Readonly
from ipylab.launcher import Launcher
from ipylab.log import IpylabLogFormatter, IpylabLogHandler, LogLevel
from ipylab.log_viewer import LogViewer
from ipylab.menu import ContextMenu, MainMenu
from ipylab.notification import NotificationManager
from ipylab.sessions import SessionManager
from ipylab.shell import Shell
from ipylab.widgets import Panel

if TYPE_CHECKING:
    from asyncio import Task
    from typing import ClassVar


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
    DISABLE_MATCHERS = (
        "IPCompleter.latex_name_matcher",
        "IPCompleter.unicode_name_matcher",
        "back_latex_name_matcher",
        "back_unicode_name_matcher",
        "IPCompleter.fwd_unicode_matcher",
        "IPCompleter.magic_config_matcher",
        "IPCompleter.magic_color_matcher",
        "IPCompleter.magic_matcher",
        "IPCompleter.file_matcher",
    )
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
    context_menu = Readonly(ContextMenu, sub_attrs=["commands"], commands=lambda app: app.commands)
    sessions = Readonly(SessionManager)

    connections: Container[tuple[ShellConnection, ...]] = TypedTuple(trait=Instance(ShellConnection))

    logging_handler: Instance[IpylabLogHandler | None] = Instance(IpylabLogHandler, allow_none=True)  # type: ignore
    log_viewer: Instance[LogViewer] = Instance(Panel, allow_none=True)  # type: ignore
    log_level = UseEnum(LogLevel, LogLevel.ERROR)

    namespaces: Container[dict[str, LastUpdatedDict]] = Dict(read_only=True)  # type: ignore
    _completers: Container[dict[str, IPC.IPCompleter]] = Dict(read_only=True)  # type: ignore

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
        handler.setFormatter(IpylabLogFormatter(fmt=fmt, style="{", datefmt="%H:%M:%S"))
        return handler

    @default("log_viewer")
    def _default_log_viewer(self):
        if self.logging_handler:
            return LogViewer(self, self.logging_handler)
        return None

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
         1. An `evaluate` method call from a subclass of `Ipylab` from kernel via
            `jfem.evaluate` in the frontend.
         2. A call in the frontend to `jfem.evaluate`.
        """
        evaluate = options["evaluate"]
        if isinstance(evaluate, str):
            evaluate = {"payload": evaluate}
        ns = self.get_namespace(options.get("namespace_id", ""), buffers=buffers)
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
        return {"payload": payload, "buffers": buffers}

    def _get_completer(self, namespace_id: str):
        completer = self._completers.get(namespace_id)
        if not completer:
            self._completers[namespace_id] = completer = IPC.IPCompleter(namespace={})
            completer.set_trait("disable_matchers", self.DISABLE_MATCHERS)
        completer.namespace = self.get_namespace(namespace_id)
        return completer

    def _get_completions(self, namespace_id: str, code: str, cursor_pos: int):
        # Borrowed from `IPC._rectify_completions`
        completer = self._get_completer(namespace_id)
        with IPC.provisionalcompleter():
            completions = list(completer.completions(code, cursor_pos))
            if not completions:
                return
            new_start = min(c.start for c in completions)
            new_end = max(c.end for c in completions)
            for c in completions:
                yield IPC.Completion(
                    new_start,
                    new_end,
                    code[new_start : c.start] + c.text + code[c.end : new_end],
                    type=c.type,
                    _origin=c._origin,  # noqa: SLF001
                    signature=c.signature,
                )

    def _do_complete(self, namespace_id: str, code: str, cursor_pos: int | None):
        """Completions provided by IPython completer, using Jedi for different namespaces."""
        # Borrowed from Shell._get_completions_experimental
        completions = list(self._get_completions(namespace_id, code, len(code) if cursor_pos is None else cursor_pos))
        comps = [
            {
                "start": comp.start,
                "end": comp.end,
                "text": comp.text,
                "type": comp.type,
                "signature": comp.signature,
            }
            for comp in completions
        ]
        if completions:
            s = completions[0].start
            e = completions[0].end
            matches = [c.text for c in completions]
        else:
            s = cursor_pos
            e = cursor_pos
            matches = []
        return {
            "matches": matches,
            "cursor_end": e,
            "cursor_start": s,
            "metadata": {"_jupyter_types_experimental": comps},
            "status": "ok",
        }

    def open_console(
        self, *, insertMode=InsertMode.split_bottom, activate=True, **kwargs: Unpack[IpylabKwgs]
    ) -> Task[ShellConnection]:
        """Open a Jupyterlab console for this kernel."""
        args = {"path": self.vpath, "insertMode": insertMode, "activate": activate}
        kwargs["transform"] = {"transform": Transform.connection}
        kwargs["hooks"] = {"add_to_tuple_fwd": [(self, "connections")]}
        return self.commands.execute("console:open", args, **kwargs)

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
        globals:
            The globals namespace includes the follow symbols:
            * ipylab
            * ipywidgets
            * ipw (ipywidgets)
        """
        kwgs = {"evaluate": evaluate, "vpath": vpath, "namespace_id": namespace_id}
        return self.operation("evaluate", kwgs, **kwargs)

    def add_objects_to_ipython_namespace(self, objects: dict, *, reset=False):
        "Load objects into the IPython/console namespace."
        if reset:
            self.comm.kernel.shell.ipy_shell.reset()  # type: ignore
        self.comm.kernel.shell.push(objects)  # type: ignore


JupyterFrontEnd = App
