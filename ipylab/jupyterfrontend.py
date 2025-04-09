# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
from typing import TYPE_CHECKING, Any, Self, Unpack, final

from ipywidgets import Widget, register
from traitlets import Bool, Container, Dict, Instance, Unicode, UseEnum, default, observe
from typing_extensions import override

import ipylab
from ipylab import Ipylab
from ipylab.commands import APP_COMMANDS_NAME, CommandPalette, CommandRegistry
from ipylab.common import Fixed, IpylabKwgs, LastUpdatedDict, Obj, Singular, to_selector
from ipylab.dialog import Dialog
from ipylab.ipylab import IpylabBase
from ipylab.launcher import Launcher
from ipylab.log import IpylabLogHandler, LogLevel
from ipylab.menu import ContextMenu, MainMenu
from ipylab.notification import NotificationManager
from ipylab.sessions import SessionManager
from ipylab.shell import Shell

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import ClassVar


@final
@register
class App(Singular, Ipylab):
    """A connection to the 'app' in the frontend.

    A singleton (per kernel) not to be subclassed or closed.
    """

    DEFAULT_COMMANDS: ClassVar = {"Open console", "Show log viewer"}
    _model_name = Unicode("JupyterFrontEndModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app").tag(sync=True)
    version = Unicode(read_only=True).tag(sync=True)
    _vpath = Unicode(read_only=True).tag(sync=True)
    per_kernel_widget_manager_detected = Bool(read_only=True).tag(sync=True)

    shell = Fixed(Shell)
    dialog = Fixed(Dialog)
    notification = Fixed(NotificationManager)
    commands = Fixed(lambda _: CommandRegistry(name=APP_COMMANDS_NAME))
    launcher = Fixed(Launcher)
    main_menu = Fixed(MainMenu)
    command_pallet = Fixed(CommandPalette)
    context_menu: Fixed[Self, ContextMenu] = Fixed(lambda c: ContextMenu(commands=c["owner"].commands))
    sessions = Fixed(SessionManager)

    logging_handler: Fixed[Self, IpylabLogHandler] = Fixed(
        lambda c: ipylab.plugin_manager.hook.get_logging_handler(app=c["owner"]),
        created=lambda c: c["owner"].shell.log_viewer,
    )
    log_level = UseEnum(LogLevel, LogLevel.ERROR)
    asyncio_loop: Instance[asyncio.AbstractEventLoop | None] = Instance(asyncio.AbstractEventLoop, allow_none=True)  # type: ignore

    namespaces: Container[dict[str, LastUpdatedDict]] = Dict(read_only=True)  # type: ignore

    @override
    def close(self, *, force=False):
        if force:
            super().close()

    @default("asyncio_loop")
    def _default_asyncio_loop(self):
        return ipylab.plugin_manager.hook.get_asyncio_event_loop(app=self)

    @observe("_ready", "log_level")
    def _app_observe_ready(self, change):
        if change["name"] == "_ready" and self._ready:
            assert self._vpath, "Vpath should always before '_ready'."  # noqa: S101
            self._selector = to_selector(self._vpath)
            ipylab.plugin_manager.hook.autostart._call_history.clear()  # type: ignore  # noqa: SLF001
            try:
                if not ipylab.plugin_manager.hook.autostart_once._call_history:  # noqa: SLF001
                    ipylab.plugin_manager.hook.autostart_once.call_historic(
                        kwargs={"app": self}, result_callback=self._autostart_callback
                    )
                ipylab.plugin_manager.hook.autostart.call_historic(
                    kwargs={"app": self}, result_callback=self._autostart_callback
                )
            except Exception as e:
                self.log.exception("Error with autostart", exc_info=e)
        if self.logging_handler:
            self.logging_handler.setLevel(self.log_level)

    def _autostart_callback(self, result):
        if inspect.iscoroutine(result):
            self.start_coro(result)

    @property
    def repr_info(self):
        return {"vpath": self._vpath}

    @property
    def repr_log(self):
        "A representation to use when logging"
        return self.__class__.__name__

    @property
    def vpath(self):
        """The virtual path for this kernel.

        `vpath` is equivalent to the session `path` in the frontend.

        Raises
        ------
        RuntimeError
            If App is not ready.

        Returns
        -------
        str
            Virtual path to the application.
        """
        if not self._ready:
            msg = "`vpath` cannot not be accessed until app is ready."
            raise RuntimeError(msg)
        return self._vpath

    @property
    def selector(self):
        """The default selector based on the `vpath` for this kernel.

        Raises
        ------
        RuntimeError
            If the application is not ready.
        """
        if not self._ready:
            msg = "`vpath` cannot not be accessed until app is ready."
            raise RuntimeError(msg)
        return self._selector

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        match operation:
            case "evaluate":
                return await self._evaluate(payload, buffers)
            case "shell_eval":
                result = await self._evaluate(payload, buffers)
                widget = result.get("payload")
                if not isinstance(widget, Widget):
                    msg = f"Expected an Widget but got {type(widget)}"
                    raise TypeError(msg)
                return await self.shell.add(widget, **payload)

        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def shutdown_kernel(self, vpath: str | None = None):
        "Shutdown the kernel"
        await self.operation("shutdownKernel", {"vpath": vpath})

    def start_iyplab_python_kernel(self, *, restart=False):
        "Start the 'ipylab' Python kernel."
        return self.operation("startIyplabKernel", {"restart": restart})

    def get_namespace(self, namespace_id="", **objects) -> LastUpdatedDict:
        """Get the namespace corresponding to namespace_id.

        The namespace is a `LastUpdatedDict` that maintains the order by which
        items are added.

        Default oubjects are added to the namespace via the plugin hook
        `default_namespace_objects`.

        Note:
            To remove a namespace call `app.namespaces.pop(<namespace_id>)`.

        The default namespace `""` will also load objects from `shell.user_ns` if
        the kernel is an ipykernel (the default kernel provided in Jupyterlab).

        Parameters
        ----------
            namespace_id: str
                The identifier for the namespace to use in this kernel.
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

    async def _evaluate(self, options: dict[str, Any], buffers: list):
        """Evaluate code for `evaluate`.

        A call to this method should originate from a call to `evaluate` from
        app in another kernel. The call is sent as a message via the frontend."""
        try:
            evaluate = options["evaluate"]
            if isinstance(evaluate, str):
                evaluate = (evaluate,)
            namespace_id = options.get("namespace_id", "")
            ns = self.get_namespace(namespace_id, buffers=buffers)
            for row in evaluate:
                name, expression = ("payload", row) if isinstance(row, str) else row
                try:
                    result = eval(expression, ns)  # noqa: S307
                except SyntaxError:
                    exec(expression, ns)  # noqa: S102
                    result = next(reversed(ns.values()))  # Requires: LastUpdatedDict
                if not name:
                    continue
                while callable(result) or inspect.isawaitable(result):
                    if callable(result):
                        kwgs = {}
                        for p in inspect.signature(result).parameters:
                            if p in options:
                                kwgs[p] = options[p]
                            elif p in ns:
                                kwgs[p] = ns[p]
                        # We use a partial so that we can evaluate with the same namespace.
                        ns["_partial_call"] = functools.partial(result, **kwgs)
                        result = eval("_partial_call()", ns)  # type: ignore # noqa: S307
                        ns.pop("_partial_call")
                    if inspect.isawaitable(result):
                        result = await result
                if name:
                    ns[name] = result
            buffers = ns.pop("buffers", [])
            payload = ns.pop("payload", None)
            if payload is not None:
                ns["_call_count"] = n = ns.get("_call_count", 0) + 1
                ns[f"payload_{n}"] = payload
            if namespace_id == "":
                self.shell.add_objects_to_ipython_namespace(ns)
        except BaseException as e:
            if isinstance(e, NameError):
                e.add_note("Tip: Check for missing an imports?")
            raise
        else:
            return {"payload": payload, "buffers": buffers}

    async def evaluate(
        self,
        evaluate: str | inspect._SourceObjectType | Iterable[str | tuple[str, str | inspect._SourceObjectType]],
        *,
        vpath: str,
        namespace_id="",
        kwgs: None | dict = None,
        **kwargs: Unpack[IpylabKwgs],
    ):
        """Evaluate code asynchronously in the 'vpath' Python kernel.

        Execution is coordinated via the frontend and will evaluate/execute the
        code specified. Most forms of expressions are acceptable. Awaitiables
        will be awaited recursively prior to sending the result.

        Parameters
        ----------
        evaluate: str | code | Iterable[str | tuple[str|None, str | code]]
            An expression or list of expressions to evaluate.

            The following combinations are acceptable:
            1. code    # Shorthand version                  -> payload = code
            2. [("payload", code)]                          -> payload = code
            3. [("payload", code1), ("", code2), code3]     -> payload = code3

            * Code is handled as a list of mappings of `symbol name` to expressions.
            [(symbol name, expression), ...]
            * The shorthand version is changed to a single element list automatically.
            * `code` is changed to ("payload", code) automatically.
            * The latest defined `"payload"` is the return value from evaluation.

            Each expression will be evaluated and if a syntax error occurs in evaluation
            it will instead be executed. The latest set symbol is taken as the execution
            result.

            If the result is callable or awaitable it will be called or await recursively
            until the result or awaitable is no longer callable or awaitable. To prevent this
            make the symbol name an empty string.

            References
            ----------
            * eval: https://docs.python.org/3/library/functions.html#eval
            * exec: https://docs.python.org/3/library/functions.html#exec

            Once evaluation is complete, the symbols named `payload` and `buffers`
            will be returned.
        vpath:
            The path of kernel session where the evaluation should take place.
        namespace_id:
            The namespace where to perform evaluation.
            The default namespace will also update the shell.user_ns after
            successful evaluation.
        kwgs: dict | None
            Specify kwgs that may be used when calling a callable.
            Note:The namespace is also searched.

        Examples
        --------
        simple:
        ``` python
        task = app.evaluate(
            "app.shell.open_console",
            vpath="test",
            kwgs={"mode": ipylab.InsertMode.split_right, "activate": False},
        )
        # The task result will be a ShellConnection. Closing the connection should
        # also close the console that was opened.
        ```

        Advanced example:
        ``` python
        async def do_something(widget, area):
            p = iplab.panel(content=widget)
            return p.add_to_shell()


        task = app.evaluate(
            [("widget", "ipw.Dropdown()"), do_something],
            area=iplab.Area.right,
            vpath="test",
        )
        # Task result should be a ShellConnection
        ```
        """
        await self.ready()
        kwgs = (kwgs or {}) | {"evaluate": evaluate, "vpath": vpath or self.vpath, "namespace_id": namespace_id}
        return await self.operation("evaluate", kwgs=kwgs, **kwargs)


JupyterFrontEnd = App
