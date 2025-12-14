# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.


from __future__ import annotations

import functools
import inspect
import json
import uuid
from types import CoroutineType
from typing import TYPE_CHECKING, Any

import anyio
import traitlets
from aiologic import Event
from async_kernel import Caller, Pending
from async_kernel.caller import truncated_rep
from async_kernel.common import Fixed
from IPython import get_ipython  # pyright: ignore[reportPrivateImportUsage]
from ipywidgets import TypedTuple, Widget, register
from traitlets import Container, Dict, Int, List, TraitType, Unicode, observe
from typing_extensions import override

import ipylab._frontend as _fe
from ipylab.common import HasApp, IpylabKwgs, Obj, P, SignalCallbackData, T, Transform, TransformType, pack

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import CoroutineType
    from typing import Self, Unpack


__all__ = ["Ipylab", "IpylabBase", "WidgetBase"]

WAIT_READY = True  # Intended for testing when there is not frontend, hence ready will never be set.


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
    "The base class for all Widgets defined in Ipylab."

    _model_name = None  # Ensure this gets overloaded
    _model_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _model_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)
    _view_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _view_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)
    _comm = None

    @observe("comm")
    def _observe_comm(self, _: dict):
        if not self.comm:
            self.close()


@register
class Ipylab(HasApp, WidgetBase):
    """
    A base class for Ipylab widgets.

    Ipylab provides a base class for creating interactive widgets that
    communicate with a corresponding frontend component. It handles
    message passing, asynchronous operations, and signal handling.
    """

    _model_name = Unicode("IpylabModel", help="Name of the model.", read_only=True).tag(sync=True)
    _python_class = Unicode().tag(sync=True)
    ipylab_base = IpylabBase(Obj.this, "").tag(sync=True)
    _ready_event: Fixed[Self, Event] = Fixed(Event)
    _view_count = Int().tag(sync=True)
    _on_ready_callbacks: Container[list[Callable[[Self], None | CoroutineType]]] = List(trait=traitlets.Callable())
    _comm = None
    _ipylab_init_complete = False
    _pending_operations: Dict[str, Pending] = Dict()
    _signal_dottednames = TypedTuple().tag(sync=True)
    _signal_callbacks: Dict[str, list[Callable[[SignalCallbackData], None | CoroutineType]]] = Dict()

    @property
    def repr_info(self) -> dict[str, Any] | str:
        "Extra info to provide for __repr__."
        return {}

    def __init__(self, **kwgs) -> None:
        if self._ipylab_init_complete:
            return
        for k, v in kwgs.items():
            if self.has_trait(k):
                self.set_trait(k, v)
        self.set_trait("_python_class", self.__class__.__name__)
        self.on_msg(self._on_custom_msg)
        super().__init__()
        self._ipylab_init_complete = True

    def __repr__(self) -> str:
        if not self._repr_mimebundle_:
            status = "CLOSED"
        elif not self._ready_event:
            status = "Not ready"
        else:
            status = ""
        try:
            info = truncated_rep.repr(self.repr_info)
        except Exception:
            info = "--info not available--"
        if status:
            return f"< {status}: {self.__class__.__name__}({info}) >"
        return f"{status}{self.__class__.__name__}({info})"

    @override
    def close(self) -> None:
        if self.comm:
            self._ipylab_send("close")
        super().close()
        self._ready_event.set()
        for k in ["_on_ready_callbacks", "_signal_callbacks"]:
            if self.trait_has_value(k):
                getattr(self, k).clear()

    @classmethod
    def get_kernel_client_id(cls) -> str:
        """Get the kernel connection `clientId` from the current message context.

        This can be used to determine the kernel connection from which the message originated."""
        return get_ipython().kernel.get_parent()["header"]["session"]  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]

    def _ipylab_send(self, content, buffers: list | None = None) -> None:
        try:
            self.send(
                {
                    "ipylab": json.dumps(content, default=pack),
                },
                buffers,
            )
        except Exception as e:
            self.log.exception("Send error", exc_info=e)
            raise

    def _call_on_ready_callback(self, callback: Callable[[Self], None | CoroutineType]):
        self.call_later(0, callback, self)

    def call_later(
        self,
        delay: float,
        func: Callable[P, T | CoroutineType[Any, Any, T]],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Pending[T]:
        "Schedule `func` to be called in the event loop of the main thread with a `delay`."
        pen = Caller("MainThread").call_later(delay, func, *args, **kwargs)
        pen.add_done_callback(functools.partial(self.on_done_log))
        return pen

    def on_done_log(self, pen: Pending, description=""):
        "A done callback used by `Ipylab.call_later`"
        if pen.cancelled():
            self.log.debug("Cancelled %s", pen)
        if e := pen.exception():
            self.log.exception(description, exc_info=e)

    def _on_custom_msg(self, _, msg: dict, buffers: list) -> None:
        """Handle incoming custom messages.

        This method is called when a custom message is received from the frontend.
        It parses the message content and performs actions based on the message type.

        Args:
            _: The socket object (not used).
            msg: The message dictionary received from the frontend.
            buffers: A list of binary buffers associated with the message.
        """
        if not (content := msg.get("ipylab")):
            return
        try:
            match json.loads(content):
                case {"ipylab_PY": str(key), "error": str(error), **payload}:
                    self._set_result(key=key, error=error, payload=payload)
                case {"ipylab_PY": str(key), **rest}:
                    self._set_result(key=key, error=None, payload=rest.get("payload"))
                case {"ipylab_FE": str(key), "operation": operation, "payload": payload}:
                    kwgs = {"key": key, "operation": operation, "payload": payload, "buffers": buffers}
                    self.call_later(0, self._do_operation_for_fe, **kwgs)
                case {"error": msg}:
                    self.log.error(msg)
                case "ready":
                    self._on_ready()
                case "closed":
                    self.close()
                case {"signal": {"dottedname": dottedname, **rest}}:
                    data = SignalCallbackData(owner=self, dottedname=dottedname, args=rest.get("args"))
                    self.call_later(0, self._notify_signal, data=data)
                case _ as data:
                    self.log.error(f"Unhandled custom message {data=}")  # noqa: G004
        except Exception as e:
            self.log.exception("Message processing error", exc_info=e)

    def _on_ready(self):
        self._ready_event.set()
        for cb in self._on_ready_callbacks:
            self.call_later(0, self._call_on_ready_callback, cb)

    def _set_result(self, key: str, error: str | None, payload: Any) -> None:
        if pen := self._pending_operations.pop(key, None):
            if error is not None:
                msg = f"An error occurred in the frontend (javascript) {error=} {payload}"
                error_ = IpylabFrontendError(msg)
                error_.add_note(f"Exception request content = {pen.metadata}")
                payload = error_
                pen.set_exception(error_)
            else:
                pen.set_result(payload)
        elif not error:
            self.log.debug("Already processed key='%s' payload=%s", key, payload)

    async def _do_operation_for_fe(self, key: str, operation: str, payload: dict, buffers: list | None) -> None:
        """Handle operation requests from the frontend and reply with a result."""
        await self.wait_ready()
        content: dict[str, Any] = {"ipylab_FE": key}
        buffers = []
        try:
            result = await self._do_operation_for_frontend(operation, payload, buffers)
            if isinstance(result, dict) and "buffers" in result:
                buffers = result["buffers"]
                result = result["payload"]
            content["payload"] = result
        except anyio.get_cancelled_exc_class():
            content["error"] = "Cancelled"
        except Exception as e:
            content["error"] = f"{e.__class__.__name__}: {e}"
            self.log.exception("Frontend operation", exc_info=e)
        finally:
            self._ipylab_send(content, buffers)

    async def _notify_signal(self, data: SignalCallbackData[Self]) -> None:
        if callbacks := self._signal_callbacks.get(data["dottedname"]):
            for callback in callbacks:
                try:
                    result: CoroutineType[Any, Any, Any] | None = callback(data)
                    if inspect.iscoroutine(result):
                        await result
                except Exception as e:
                    self.log.exception("Signal callback", exc_info=e)

    async def _obj_operation(self, base: Obj, subpath: str, operation: str, kwgs, kwargs: IpylabKwgs) -> Any:
        await self.wait_ready()
        kwgs |= {"genericOperation": operation, "basename": base, "subpath": subpath}
        return await self.operation("genericOperation", kwgs=kwgs, **kwargs)

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        """Perform an operation for a custom message with an ipylab_FE uuid."""
        # Overload as required
        raise NotImplementedError(operation)

    async def wait_ready(self) -> Self:
        """Wait for the instance to be ready."""
        self._check_closed()
        if WAIT_READY:
            if self is not self.app:
                await self.app.wait_ready()
            await self._ready_event
            self._check_closed()
        return self

    def on_ready(self, callback: Callable[[Self], None | CoroutineType], remove=False) -> None:
        """
        Register a historic callback to execute when the frontend indicates
        it is ready.

        `historic` meaning that the callback will be called immediately if the
        instance is already ready.

        It will be called when the instance is first created, and subsequently
        when the fronted is reloaded, such as when the page is refreshed or the
        workspace is reloaded.

        The callback will be executed only once.

        Args:
            callback : The callback to execute when the application is ready.
        remove : If True, remove the callback from the list of callbacks.
            By default, False.
        """
        if not remove and callback not in self._on_ready_callbacks:
            self._on_ready_callbacks.append(callback)
            if self._ready_event:
                self._call_on_ready_callback(callback)
        elif callback in self._on_ready_callbacks:
            self._on_ready_callbacks.remove(callback)

    async def operation(
        self,
        operation: str,
        kwgs: dict | None = None,
        *,
        transform: TransformType = Transform.auto,
        toLuminoWidget: list[str] | None = None,
        toObject: list[str] | None = None,
    ) -> Any:
        """
        Perform an operation in the frontend.

        Args:
            operation: Name corresponding to operation in JS frontend.
            transform: The transform to apply to the result of the operation.
                see: ipylab.Transform
            toLuminoWidget: A list of item name mappings to convert to a Lumino widget in the frontend
                prior to performing the operation.
            toObject: A list of item name mappings to convert to objects in the frontend prior
                to performing the operation.
        """
        await self.wait_ready()
        if not operation or not isinstance(operation, str):
            msg = f"Invalid {operation=}"
            raise ValueError(msg)
        ipylab_PY = str(uuid.uuid4())
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

        self._pending_operations[ipylab_PY] = pen = Pending()
        pen.metadata.update(content=content)
        self._ipylab_send(content)
        try:
            return await Transform.transform_payload(transform=content["transform"], payload=await pen)
        except Exception as e:
            self.log.exception("Operation error", exc_info=e)
            raise

    async def execute_method(self, subpath: str, args: tuple = (), obj=Obj.base, **kwargs: Unpack[IpylabKwgs]) -> Any:
        """
        Execute a method on a remote object in the frontend.

        Args:
            subpath: The path to the method to execute, relative to the object.
            args: The positional arguments to pass to the method, by default ().
            obj: The object on which to execute the method, by default Obj.base.
            kwargs: The keyword arguments to pass to the method.

        Returns:
            The result of the method call.
        """
        return await self._obj_operation(obj, subpath, "executeMethod", {"args": args}, kwargs)

    async def get_property(
        self, subpath: str, *, obj=Obj.base, null_if_missing=False, **kwargs: Unpack[IpylabKwgs]
    ) -> Any:
        """
        Get a property from an object in the frontend.

        Args:
            subpath: The path to the property to get, e.g. "foo.bar".
            obj: The object to get the property from.
            null_if_missing: If True, return None if the property is missing.
            kwargs: Keyword arguments to pass to the Javascript function.

        Returns:
            The value of the property.
        """
        return await self._obj_operation(obj, subpath, "getProperty", {"null_if_missing": null_if_missing}, kwargs)

    async def set_property(self, subpath: str, value, *, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]) -> None:
        """Set a property of an object in the frontend.

        Args:
            subpath: The path to the property to get, e.g. "foo.bar".
            obj: The object to get the property from.
            null_if_missing: If True, return None if the property is missing.
            kwargs: Keyword arguments to pass to the Javascript function.
        """
        return await self._obj_operation(obj, subpath, "setProperty", {"value": value}, kwargs)

    async def update_property(
        self, subpath: str, value: dict[str, Any], *, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]
    ) -> dict[str, Any]:
        """Update a property of an object in the frontend equivalent to a `dict.update` call.

        Args:
            subpath: The path to the property to get, e.g. "foo.bar".
            obj: The object to get the property from.
            null_if_missing: If True, return None if the property is missing.
            kwargs: Keyword arguments to pass to the Javascript function.

        Returns:
            The updated property.
        """
        return await self._obj_operation(obj, subpath, "updateProperty", {"value": value}, kwargs)

    async def list_properties(
        self, subpath="", *, obj=Obj.base, depth=3, skip_hidden=True, **kwargs: Unpack[IpylabKwgs]
    ) -> dict[str, Any]:
        """
        List properties of a given object in the frontend.

        Args:
            subpath (str, optional): Subpath to the object. Defaults to "".
            obj (Obj, optional): Object to list properties from. Defaults to Obj.base.
            depth (int, optional): Depth of the inheritance introspection on the object in the front. Defaults to 3.
            skip_hidden (bool, optional): Whether to skip hidden properties. Defaults to True.
            **kwargs (Unpack[IpylabKwgs]): Additional keyword arguments.

        Returns:
            Dictionary of properties.
        """
        kwgs = {"depth": depth, "omitHidden": skip_hidden}
        return await self._obj_operation(obj, subpath, "listProperties", kwgs, kwargs)

    @classmethod
    def _list_signals(cls, obj, *, prefix="") -> Generator[str | Any, Any, None]:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "<signals>":
                    for signal in v:
                        yield f"{prefix}.{signal}".strip(".")
                elif isinstance(v, dict):
                    yield from cls._list_signals(v, prefix=f"{prefix}.{k}".strip("."))

    def register_signal_callback(
        self, dottedname: str, callback: Callable[[SignalCallbackData[Self]], None | CoroutineType], *, remove=False
    ) -> None:
        """
        Registers a callback function to be executed when a specific signal is emitted.

        The signal is identified by its dotted name (e.g., 'shell.activeChanged').
        The callback function will receive a `SignalCallbackData` object as its argument,
        containing information about the signal.

        Callbacks are executed in the order in which they are registered, if the callback is a coroutine
        it will be awaited directly after it is called.

        To find a list of available signals used the methods `list_signals` and `list_view_signals`.

        Args:
            dottedname: The dotted name of the signal to listen for.
            callback: The callable to execute when the signal is emitted.
                      It should accept a `SignalCallbackData` object as its argument.
                      It can be a regular function or a coroutine.
            remove: If True, remove the callback from the list of callbacks for the signal.
                    If False (default), add the callback to the list.
        """
        if not (callbacks := self._signal_callbacks.get(dottedname)):
            self._signal_callbacks[dottedname] = callbacks = []
        if remove:
            if callback in callbacks:
                callbacks.remove(callback)
        elif callback not in callbacks:
            callbacks.append(callback)
        dottednames = {*self._signal_dottednames, dottedname}
        if not callbacks:
            dottednames.discard(dottedname)
        self.set_trait("_signal_dottednames", tuple(sorted(dottednames)))

    async def list_signals(self, depth=3) -> list[str | Any]:
        """
        List the nested signals associated with the base in the frontend.

        !!! See also:
            - `register_signal_callback`
            - `list_view_signals`
        """
        properties = await self.list_properties(depth=depth)
        return list(self._list_signals(properties))

    async def list_view_signals(self, depth=3) -> list[str | Any]:
        """
        List the nested signals belonging to a view of this object.

        !!! note
            - This only applies to widgets that have a view.
            - To list the signals in a view, at least one view of the object must be live.

        !!! See also:
            - `register_signal_callback`
            - `list_signals`
        """
        if not (views := (await self.list_properties("views")).get("<promises>")):
            msg = f"No views found for {self}"
            raise ValueError(msg)
        properties = await self.list_properties(f"views[{views[0]}]", depth=depth)
        return list(dict.fromkeys(self._list_signals(properties, prefix="views")))
