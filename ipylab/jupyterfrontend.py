# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal, Self, Unpack, final

import async_kernel
from aiologic.meta import iscoroutinelike
from async_kernel import Caller, Kernel, utils
from async_kernel.common import Fixed
from ipywidgets import Widget, register
from traitlets import Bool, Unicode, UseEnum, observe
from typing_extensions import override

import ipylab
from ipylab import Ipylab
from ipylab.commands import APP_COMMANDS_NAME, CommandPalette, CommandRegistry
from ipylab.common import IpylabKwgs, Obj, Singular, execute_using_shells_namespace, to_selector
from ipylab.dialog import Dialog
from ipylab.ipylab import IpylabBase
from ipylab.launcher import Launcher
from ipylab.log import IpylabLogHandler, LogLevel
from ipylab.menu import ContextMenu, MainMenu
from ipylab.notification import NotificationManager
from ipylab.sessions import SessionManager
from ipylab.shell import Shell
from ipylab.toolbar import CustomToolbar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import ClassVar


@final
@register
class JupyterFrontEnd(Singular, Ipylab):
    """
    A connection to the 'app' in the frontend.

    A singleton (per kernel) not to be subclassed or closed.
    """

    DEFAULT_COMMANDS: ClassVar = {"Open console", "Show log viewer"}
    _test_mode = False
    _model_name = Unicode("JupyterFrontEndModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app").tag(sync=True)
    version = Unicode(read_only=True).tag(sync=True)
    _vpath = Unicode(read_only=True).tag(sync=True)
    per_kernel_widget_manager_detected = Bool(read_only=True).tag(sync=True)

    kernel: Fixed[Self, Kernel] = Fixed(utils.get_kernel)
    caller: Fixed[Self, Caller] = Fixed(lambda c: getattr(c["owner"].kernel, "caller", None) or Caller("MainThread"))

    shell = Fixed(Shell)
    dialog = Fixed(Dialog)
    notification = Fixed(NotificationManager)
    commands = Fixed(lambda _: CommandRegistry(name=APP_COMMANDS_NAME))
    launcher = Fixed(Launcher)
    main_menu = Fixed(MainMenu)
    command_pallet = Fixed(CommandPalette)
    context_menu: Fixed[Self, ContextMenu] = Fixed(lambda c: ContextMenu(commands=c["owner"].commands))
    sessions = Fixed(SessionManager)
    toolbar = Fixed(CustomToolbar)

    logging_handler: Fixed[Self, IpylabLogHandler] = Fixed(
        lambda c: ipylab.plugin_manager.hook.get_logging_handler(app=c["owner"])
    )
    log_level = UseEnum(LogLevel, LogLevel.ERROR)

    @override
    def close(self, *, force=False) -> None:
        if force:
            super().close()

    @observe("log_level")
    def _observe_log_level(self, _) -> None:
        if self.logging_handler:
            self.logging_handler.setLevel(self.log_level)

    @override
    async def _set_ready(self) -> None:
        await super()._set_ready()
        assert self._vpath, "'_vpath' must be set first."
        ipylab.plugin_manager.hook.autostart._call_history.clear()  # pyright: ignore[reportPrivateUsage, reportOptionalMemberAccess]
        try:
            if not ipylab.plugin_manager.hook.autostart_once._call_history:  # pyright: ignore[reportPrivateUsage]
                ipylab.plugin_manager.hook.autostart_once.call_historic(
                    kwargs={"app": self}, result_callback=self._autostart_callback
                )
            ipylab.plugin_manager.hook.autostart.call_historic(
                kwargs={"app": self}, result_callback=self._autostart_callback
            )
        except Exception as e:
            self.log.exception("Error with autostart", exc_info=e)

    def _autostart_callback(self, result) -> None:
        if iscoroutinelike(result):
            self.call_later(0, lambda: result)

    @property
    @override
    def repr_info(self) -> dict[str, str]:
        return {"vpath": self._vpath, "session name": self.session_name}

    @property
    def repr_log(self) -> str:
        "A representation to use when logging"
        return self.__class__.__name__

    @property
    def vpath(self) -> str:
        """
        The *virtual path* assigned to process in which the kernel is running.

        `vpath` is equivalent to the session `path` in the frontend and cannot be changed.
        """
        if not (vpath := self._vpath):
            msg = "`vpath` Has not yet been set! Tip: Use await app.wait_ready() (or the Ipylab object `ready` method) to avoid this error."
            raise RuntimeError(msg)
        return vpath

    @property
    def session_name(self) -> str:
        "The full path including vpath."
        return os.environ.get("JPY_SESSION_NAME", "")

    @property
    def selector(self) -> str:
        """The default selector using the current `vpath`."""
        return to_selector(self.vpath)

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        match operation:
            case "evaluate":
                return await self._evaluate(payload)
            case "shell_eval":
                result = await self._evaluate(payload)
                widget = result.get("payload")
                if not isinstance(widget, Widget):
                    msg = f"Expected an Widget but got {type(widget)}"
                    raise TypeError(msg)
                return await self.shell.add(widget, **payload)
            case _:
                return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def shutdown_kernel(self, vpath: str | None = None) -> None:
        "Shutdown the kernel."
        await self.operation("shutdownKernel", {"vpath": vpath})

    def start_iyplab_python_kernel(self, *, restart=False):
        "Start the 'ipylab' Python kernel."
        return self.operation("startIyplabKernel", {"restart": restart})

    async def _evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Evaluate code for `evaluate`.

        A call to this method should originate from a call to `evaluate` from
        app in another kernel. The call is sent as a message via the frontend.
        """

        class CatchResult(dict):
            def __setitem__(self, key, value) -> None:  # pyright: ignore[reportImplicitOverride]
                # set the result as values are written to the namespace
                nonlocal result
                user_ns.__setitem__(key, value)
                result = value

            def __getitem__(self, key):  # pyright: ignore[reportImplicitOverride]
                return user_ns.__getitem__(key)

        evaluate = payload["evaluate"]
        subshell_id = payload.get("subshell_id")
        with async_kernel.utils.subshell_context(subshell_id):
            shell = self.kernel.shell
            user_ns = shell.user_ns
            user_global_ns = shell.user_global_ns
            result = None
            if isinstance(evaluate, str):
                evaluate = (evaluate,)
            for row in evaluate:
                name, expression = ("", row) if isinstance(row, str) else row
                try:
                    source = compile(expression, "-- Evaluate --", "eval")
                except SyntaxError:
                    source = compile(expression, "-- Expression --", "exec")
                    exec(source, user_global_ns, CatchResult(shell.user_ns))
                else:
                    result = eval(source, user_global_ns, user_ns)
                if callable(result):
                    result = await execute_using_shells_namespace(
                        result, shell, payload, connection_id=payload.get("connection_id")
                    )
                if iscoroutinelike(result):
                    result = await result
                if name:
                    user_ns[name] = result

        if result is not None and payload.get("strong_ref"):
            user_ns["_ipylab_evaluate_count"] = cnt = user_ns.get("_ipylab_evaluate_count", 0) + 1
            user_ns[f"_ipylab_evaluate_{cnt}"] = result
        return {"payload": result}

    async def evaluate(
        self,
        evaluate: str | Callable | Iterable[str | tuple[str, str | Callable]],
        *,
        vpath: str = "",
        preferred_kernel: Literal["async", "python3"] | str = "async",  # noqa: PYI051
        kwgs: None | dict = None,
        strong_ref=True,
        **kwargs: Unpack[IpylabKwgs],
    ) -> Any:
        """
        Evaluate code asynchronously in the 'vpath' Python kernel.

        Execution is coordinated via the frontend and will evaluate/execute the
        code specified. Most forms of expressions are acceptable. If the last
        result of evaluation is a coroutine; then it will be awaited prior
        to sending the result.

        Args:
            evaluate:
                An expression or list of expressions to evaluate.
            vpath:
                The path of kernel session where the evaluation should take place.
            preferred_kernel:
                The name of the kernel to use if a new kernel is started.
            strong_ref:
                Keep a reference to the result to avoid garbage collection
            kwgs: dict | None
                Specify kwgs that may be used when calling a callable.
                Note:The namespace is also searched.


        The following `evaluate` argument combinations are acceptable:
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

        Examples:

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
        await self.wait_ready()
        kwgs = (kwgs or {}) | {
            "evaluate": evaluate,
            "vpath": vpath or self.vpath,
            "preferredKernel": preferred_kernel,
            "strong_ref": strong_ref,
        }
        if vpath == self.vpath:
            return await self._evaluate(kwgs)
        return await self.operation("evaluate", kwgs=kwgs, **kwargs)

    def add_objects_to_user_ns(self, subshell_id: str | None, /, **objects) -> None:
        "Load objects into the user namespace."

        with async_kernel.utils.subshell_context(subshell_id):
            self.kernel.shell.user_ns.update(objects)
