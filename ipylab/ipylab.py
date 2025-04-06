# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import uuid
import weakref
from typing import TYPE_CHECKING, Any, cast

import anyio
import traitlets
from anyio import Event, create_memory_object_stream
from ipywidgets import Widget, register
from traitlets import (
    Bool,
    Container,
    Dict,
    HasTraits,
    Instance,
    List,
    Set,
    TraitError,
    TraitType,
    Unicode,
    default,
    observe,
)

import ipylab
import ipylab._frontend as _fe
from ipylab.common import Fixed, IpylabKwgs, Obj, PosArgsT, T, Transform, TransformType, autorun, pack
from ipylab.log import IpylabLoggerAdapter, LogLevel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import CoroutineType
    from typing import Self, Unpack

    from anyio.streams.memory import MemoryObjectSendStream

__all__ = ["Ipylab", "WidgetBase"]


class IpylabBase(TraitType[tuple[str, str], None]):
    info_text = "A mapping to the base in the frontend."
    read_only = True

    def __init__(self, base: Obj, subpath: str):
        "The 'mapping' to the 'base' in the frontend."
        self._trait = Unicode()
        super().__init__((base, subpath))


class IpylabFrontendError(IOError):
    pass


class WidgetBase(Widget):
    _model_name = None  # Ensure this gets overloaded
    _model_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _model_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)
    _view_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _view_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)
    _comm = None
    add_traits = None  # type: ignore # Don't support the method HasTraits.add_traits as it creates a new type that isn't a subclass of its origin)


@register
class Ipylab(WidgetBase):
    """A base class for creating ipylab widgets.

    Ipylab widgets are Jupyter widgets that are designed to interact with the
    JupyterLab application. They provide a way to extend the functionality
    of JupyterLab with custom Python code.
    """

    _model_name = Unicode("IpylabModel", help="Name of the model.", read_only=True).tag(sync=True)
    _python_class = Unicode().tag(sync=True)
    ipylab_base = IpylabBase(Obj.this, "").tag(sync=True)
    _ready = Bool(read_only=True, help="Set to by frontend when ready").tag(sync=True)
    _on_ready_callbacks: Container[list[Callable[[Self], None | CoroutineType]]] = List(trait=traitlets.Callable())
    _ready_event = Instance(Event, ())
    _comm = None
    _ipylab_init_complete = False
    _pending_operations: Dict[str, MemoryObjectSendStream] = Dict()
    _has_attrs_mappings: Container[set[tuple[HasTraits, str]]] = Set()
    _close_extras: Fixed[Self, weakref.WeakSet[Widget]] = Fixed(weakref.WeakSet)

    log = Instance(IpylabLoggerAdapter, read_only=True)
    app = Fixed(lambda _: ipylab.App())

    @property
    def repr_info(self) -> dict[str, Any] | str:
        "Extra info to provide for __repr__."
        return {}

    @default("log")
    def _default_log(self):
        return IpylabLoggerAdapter(self.__module__, owner=self)

    def __init__(self, **kwgs):
        if self._ipylab_init_complete:
            return
        for k in kwgs:
            if self.has_trait(k):
                self.set_trait(k, kwgs[k])
        self.set_trait("_python_class", self.__class__.__name__)
        super().__init__()
        self._ipylab_init_complete = True
        self.on_msg(self._on_custom_msg)

    def __repr__(self):
        if not self._repr_mimebundle_:
            status = "CLOSED"
        elif (not self._ready) and self._repr_mimebundle_:
            status = "Not ready"
        else:
            status = ""
        info = (
            ", ".join(f"{k}={v!r}" for k, v in self.repr_info.items())
            if isinstance(self.repr_info, dict)
            else self.repr_info
        )
        if status:
            return f"< {status}: {self.__class__.__name__}({info}) >"
        return f"{status}{self.__class__.__name__}({info})"

    @observe("comm", "_ready")
    def _observe_comm(self, change: dict):
        if not self.comm:
            self.close()
        if change["name"] == "_ready" and self._ready:
            self._ready_event.set()
            self._ready_event = Event()
            for cb in self._on_ready_callbacks:
                result = cb(self)
                if inspect.iscoroutine(result):
                    self.start_coro(result)

    def close(self):
        if self.comm:
            self._ipylab_send({"close": True})
        super().close()
        for item in list(self._close_extras):
            item.close()
        for obj, name in list(self._has_attrs_mappings):
            if val := getattr(obj, name, None):
                if val is self:
                    with contextlib.suppress(TraitError):
                        obj.set_trait(name, None)
                elif isinstance(val, tuple):
                    obj.set_trait(name, tuple(v for v in val if v.comm))
        self._on_ready_callbacks.clear()

    def _check_closed(self):
        if not self._repr_mimebundle_:
            msg = f"This widget is closed {self!r}"
            raise RuntimeError(msg)

    async def catch_exceptions(self, aw: Awaitable) -> None:
        """Catches exceptions that occur when awaiting an awaitable.

        The exception is logged, but otherwise ignored.

        Args:
            aw: The awaitable to await.
        """
        try:
            await aw
        except BaseException as e:
            self.log.exception(f"Calling {aw}", obj={"aw": aw}, exc_info=e)  # noqa: G004
            if self.app.log_level == LogLevel.DEBUG:
                raise

    def _on_custom_msg(self, _, msg: dict, buffers: list):
        content = msg.get("ipylab")
        if not content:
            return
        try:
            c: dict[str, Any] = json.loads(content)
            if "ipylab_PY" in c:
                self._set_result(content=c)
            elif "ipylab_FE" in c:
                self._do_operation_for_fe(True, c["ipylab_FE"], c["operation"], c["payload"], buffers)
            elif "closed" in c:
                self.close()
            else:
                raise NotImplementedError(msg)  # noqa: TRY301
        except Exception as e:
            self.log.exception("Message processing error", obj=msg, exc_info=e)

    @autorun
    async def _set_result(self, content: dict[str, Any]):
        send_stream = self._pending_operations.pop(content["ipylab_PY"])
        if error := content.get("error"):
            e = IpylabFrontendError(error)
            e.add_note(f"{content=}")
            value = e
        else:
            value = content.get("payload")
        await send_stream.send(value)

    @autorun
    async def _do_operation_for_fe(self, ipylab_FE: str, operation: str, payload: dict, buffers: list | None):
        """Handle operation requests from the frontend and reply with a result."""
        await self.ready()
        content: dict[str, Any] = {"ipylab_FE": ipylab_FE}
        buffers = []
        try:
            result = await self._do_operation_for_frontend(operation, payload, buffers)
            if isinstance(result, dict) and "buffers" in result:
                buffers = result["buffers"]
                result = result["payload"]
            content["payload"] = result
        except asyncio.CancelledError:
            content["error"] = "Cancelled"
        except Exception as e:
            self.log.exception("Frontend operation", obj={"operation": operation, "payload": payload}, exc_info=e)
        finally:
            self._ipylab_send(content, buffers)

    async def _obj_operation(self, base: Obj, subpath: str, operation: str, kwgs, kwargs: IpylabKwgs):
        await self.ready()
        kwgs |= {"genericOperation": operation, "basename": base, "subpath": subpath}
        return await self.operation("genericOperation", kwgs=kwgs, **kwargs)

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        """Perform an operation for a custom message with an ipylab_FE uuid."""
        # Overload as required
        raise NotImplementedError(operation)

    async def ready(self) -> Self:
        """Wait for the instance to be ready.

        If this is not the main application instance, it waits for the
        main application instance to be ready first.
        """
        self._check_closed()
        if not self._ready:
            await self._ready_event.wait()
        return self

    def on_ready(self, callback, remove=False):  # noqa: FBT002
        """Register a callback to execute when the application is ready.

        The callback will be executed only once.

        Parameters
        ----------
        callback : callable
            The callback to execute when the application is ready.
        remove : bool, optional
            If True, remove the callback from the list of callbacks.
            By default, False.
        """
        if not remove:
            self._on_ready_callbacks.append(callback)
        elif callback in self._on_ready_callbacks:
            self._on_ready_callbacks.remove(callback)

    def add_to_tuple(self, owner: HasTraits, name: str):
        """Add self to the tuple of obj."""

        items = getattr(owner, name)
        if self.comm and self not in items:
            owner.set_trait(name, (*items, self))
        # see: _observe_comm for removal
        self._has_attrs_mappings.add((owner, name))

    def add_as_trait(self, obj: HasTraits, name: str):
        "Add self as a trait to obj."
        self._check_closed()
        obj.set_trait(name, self)
        # see: _observe_comm for removal
        self._has_attrs_mappings.add((obj, name))

    def close_with_self(self, obj: Widget):
        "Close the widget when self closes. If self is already closed, object will be closed immediately."
        if not self.comm:
            obj.close()
            msg = f"{self} is closed"
            raise anyio.ClosedResourceError(msg)
        self._close_extras.add(obj)

    def _ipylab_send(self, content, buffers: list | None = None):
        try:
            self.send({"ipylab": json.dumps(content, default=pack)}, buffers)
        except Exception as e:
            self.log.exception("Send error", obj=content, exc_info=e)
            raise

    def start_coro(self, coro: CoroutineType[None, None, T]) -> None:
        """Start a coroutine in the main event loop.

        If the kernel has a `start_soon` method, use it to start the coroutine.
        Otherwise, if the application has an asyncio loop, use
        `asyncio.run_coroutine_threadsafe` to start the coroutine in the loop.
        If neither of these is available, raise a RuntimeError.

        Tip: Use anyio primiatives in the coroutine to ensure it will run in
        the chosen backend of the kernel.

        Parameters
        ----------
        coro : CoroutineType[None, None, T]
            The coroutine to start.

        Raises
        ------
        RuntimeError
            If there is no running loop to start the task.
        """

        self._check_closed()
        self.start_soon(self.catch_exceptions, coro)

    def start_soon(self, func: Callable[[Unpack[PosArgsT]], CoroutineType], *args: Unpack[PosArgsT]):
        """Start a function soon in the main event loop.

        If the kernel has a start_soon method, use it.
        Otherwise, if the app has an asyncio loop, run the function in that loop.
        Otherwise, raise a RuntimeError.

        This is a simple wrapper to ensure the function is called in the main
        event loop. No error reporting is done.

        Consider using start_coro which performs additional checks and automatically
        logs exceptions.
        """
        try:
            start_soon = self.comm.kernel.start_soon  # type: ignore
        except AttributeError:
            if loop := self.app.asyncio_loop:
                coro = func(*args)
                asyncio.run_coroutine_threadsafe(coro, loop)
            else:
                msg = f"We don't have a running loop to run {func}"
                raise RuntimeError(msg) from None
        else:
            start_soon(func, *args)

    async def operation(
        self,
        operation: str,
        kwgs: dict | None = None,
        *,
        transform: TransformType = Transform.auto,
        toLuminoWidget: list[str] | None = None,
        toObject: list[str] | None = None,
    ) -> Any:
        """Perform an operation in the frontend.

        operation: str
            Name corresponding to operation in JS frontend.

        transform : Transform | dict
            The transform to apply to the result of the operation.
            see: ipylab.Transform

        toLuminoWidget: List[str] | None
            A list of item name mappings to convert to a Lumino widget in the frontend
            prior to performing the operation.

        toObject:  List[str] | None
            A list of item name mappings to convert to objects in the frontend prior
            to performing the operation.
        """
        # validation
        await self.ready()
        if not operation or not isinstance(operation, str):
            msg = f"Invalid {operation=}"
            raise ValueError(msg)
        ipylab_PY = str(uuid.uuid4())  # noqa: N806
        content = {
            "ipylab_PY": ipylab_PY,
            "operation": operation,
            "kwgs": dict(kwgs) if kwgs else {},
            "transform": Transform.validate(transform),
        }
        if toLuminoWidget:
            content["toLuminoWidget"] = toLuminoWidget
        if toObject:
            content["toObject"] = toObject

        send_stream, receive_stream = create_memory_object_stream()
        self._pending_operations[ipylab_PY] = send_stream
        self._ipylab_send(content)
        result = await receive_stream.receive()
        if isinstance(result, Exception):
            raise result
        result = await Transform.transform_payload(content["transform"], result)
        return cast(Any, result)

    async def execute_method(self, subpath: str, args: tuple = (), obj=Obj.base, **kwargs: Unpack[IpylabKwgs]) -> Any:
        return await self._obj_operation(obj, subpath, "executeMethod", {"args": args}, kwargs)

    async def get_property(self, subpath: str, *, obj=Obj.base, null_if_missing=False, **kwargs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "getProperty", {"null_if_missing": null_if_missing}, kwargs)

    async def set_property(self, subpath: str, value, *, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]):
        return await self._obj_operation(obj, subpath, "setProperty", {"value": value}, kwargs)

    async def update_property(self, subpath: str, value: dict[str, Any], *, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]):
        return await self._obj_operation(obj, subpath, "updateProperty", {"value": value}, kwargs)

    async def list_properties(
        self, subpath="", *, obj=Obj.base, depth=3, skip_hidden=True, **kwargs: Unpack[IpylabKwgs]
    ) -> dict:
        kwgs = {"depth": depth, "omitHidden": skip_hidden}
        return await self._obj_operation(obj, subpath, "listProperties", kwgs, kwargs)
