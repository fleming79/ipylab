# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from typing import TYPE_CHECKING, Any, cast

import traitlets
from anyio import Event, create_memory_object_stream
from ipywidgets import TypedTuple, Widget, register
from traitlets import Bool, Container, Dict, Instance, Int, List, TraitType, Unicode, observe
from typing_extensions import override

import ipylab._frontend as _fe
from ipylab.common import HasApp, IpylabKwgs, Obj, SignalCallbackData, Transform, TransformType, autorun, pack

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CoroutineType
    from typing import Self, Unpack

    from anyio.streams.memory import MemoryObjectSendStream

__all__ = ["Ipylab", "IpylabBase", "WidgetBase"]


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
    """Base class for ipylab widgets.

    Inherits from HasApp and Widget.

    Attributes:
        _model_name (Unicode): The name of the model. Must be overloaded.
        _model_module (Unicode): The module name of the model.
        _model_module_version (Unicode): The module version of the model.
        _view_module (Unicode): The module name of the view.
        _view_module_version (Unicode): The module version of the view.
        _comm (Comm): The comm object.

    """

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
    """A base class for creating ipylab widgets that inherit from an IpylabModel
    in the frontend.

    Ipylab widgets are Jupyter widgets that are designed to interact with the
    JupyterLab application. They provide a way to extend the functionality
    of JupyterLab with custom Python code.
    """

    _model_name = Unicode("IpylabModel", help="Name of the model.", read_only=True).tag(sync=True)
    _python_class = Unicode().tag(sync=True)
    ipylab_base = IpylabBase(Obj.this, "").tag(sync=True)
    _ready = Bool(read_only=True, help="Set to by frontend when ready").tag(sync=True)
    _view_count = Int().tag(sync=True)
    _on_ready_callbacks: Container[list[Callable[[Self], None | CoroutineType]]] = List(trait=traitlets.Callable())
    _ready_event = Instance(Event, ())
    _comm = None
    _ipylab_init_complete = False
    _pending_operations: Dict[str, MemoryObjectSendStream] = Dict()
    _signal_dottednames = TypedTuple().tag(sync=True)
    _signal_callbacks: Dict[str, list[Callable[[SignalCallbackData], None | CoroutineType]]] = Dict()

    @property
    def repr_info(self) -> dict[str, Any] | str:
        "Extra info to provide for __repr__."
        return {}

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

    @observe("_ready")
    def _observe_ready(self, _: dict):
        if self._ready:
            self._ready_event.set()
            self._ready_event = Event()
            for cb in self._on_ready_callbacks:
                self._call_ready_callback(cb)

    @override
    def close(self):
        if self.comm:
            self._ipylab_send({"close": True})
        super().close()
        for k in ["_on_ready_callbacks", "_signal_callbacks"]:
            if self.trait_has_value(k):
                getattr(self, k).clear()

    def _ipylab_send(self, content, buffers: list | None = None):
        try:
            self.send({"ipylab": json.dumps(content, default=pack)}, buffers)
        except Exception as e:
            self.log.exception("Send error", obj=content, exc_info=e)
            raise

    def _on_custom_msg(self, _, msg: dict, buffers: list):
        """Handle incoming custom messages.

        This method is called when a custom message is received from the frontend.
        It parses the message content and performs actions based on the message type.

        Args:
            _: The socket object (not used).
            msg (dict): The message dictionary received from the frontend.
            buffers (list): A list of binary buffers associated with the message.
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
                    self._do_operation_for_fe(key=key, operation=operation, payload=payload, buffers=buffers)
                case {"closed": closed} if closed:
                    self.close()
                case {"signal": {"dottedname": dottedname, **rest}}:
                    data = SignalCallbackData(owner=self, dottedname=dottedname, args=rest.get("args"))
                    self._notify_signal(data=data)
                case _ as data:
                    self.log.error(f"Unhandled custom message {data=}", obj=data)  # noqa: G004
        except Exception as e:
            self.log.exception("Message processing error", obj=msg, exc_info=e)

    @autorun
    async def _set_result(self, key: str, error: str | None, payload: Any):
        # We use autorun to ensure this code is run in the main event loop
        send_stream = self._pending_operations.pop(key)
        if error is not None:
            error_ = IpylabFrontendError(error)
            error_.add_note(f"{payload=}")
            payload = error_
        send_stream.send_nowait(payload)

    @autorun
    async def _do_operation_for_fe(self, key: str, operation: str, payload: dict, buffers: list | None):
        """Handle operation requests from the frontend and reply with a result."""
        # We use autorun to ensure this code is run in the main event loop
        await self.ready()
        content: dict[str, Any] = {"ipylab_FE": key}
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
            content["error"] = f"{e.__class__.__name__}: {e}"
            self.log.exception("Frontend operation", obj={"operation": operation, "payload": payload}, exc_info=e)
        finally:
            self._ipylab_send(content, buffers)

    @autorun
    async def _notify_signal(self, data: SignalCallbackData):
        # We use autorun to ensure this code is run in the main event loop
        if callbacks := self._signal_callbacks.get(data["dottedname"]):
            for callback in callbacks:
                try:
                    result = callback(data)
                    if inspect.iscoroutine(result):
                        await result
                except Exception as e:
                    self.log.exception("Signal callback", obj={"callback": callback, "data": data}, exc_info=e)

    async def _obj_operation(self, base: Obj, subpath: str, operation: str, kwgs, kwargs: IpylabKwgs):
        await self.ready()
        kwgs |= {"genericOperation": operation, "basename": base, "subpath": subpath}
        return await self.operation("genericOperation", kwgs=kwgs, **kwargs)

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        """Perform an operation for a custom message with an ipylab_FE uuid."""
        # Overload as required
        raise NotImplementedError(operation)

    def _call_ready_callback(self, callback: Callable[[Self], None | CoroutineType]):
        result = callback(self)
        if inspect.iscoroutine(result):
            self.start_coro(result)

    async def ready(self) -> Self:
        """Wait for the instance to be ready.

        Returns:
            Self: The instance itself, after it is ready.
        """
        self._check_closed()
        if not self._ready:
            await self._ready_event.wait()
        return self

    def on_ready(self, callback: Callable[[Self], None | CoroutineType], remove=False):  # noqa: FBT002
        """Register a historic callback to execute when the frontend indicates
        it is ready.

        `historic` meaning that the callback will be called immediately if the
        instance is already ready.

        It will be called when the instance is first created, and subsequently
        when the fronted is reloaded, such as when the page is refreshed or the
        workspace is reloaded.

        The callback will be executed only once.

        Parameters
        ----------
        callback : callable
            The callback to execute when the application is ready.
        remove : bool, optional
            If True, remove the callback from the list of callbacks.
            By default, False.
        """
        if not remove and callback not in self._on_ready_callbacks:
            self._on_ready_callbacks.append(callback)
            if self._ready:
                self._call_ready_callback(callback)
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
        """Execute a method on a remote object in the frontend.

        Parameters
        ----------
        subpath : str
            The path to the method to execute, relative to the object.
        args : tuple, optional
            The positional arguments to pass to the method, by default ().
        obj : Obj, optional
            The object on which to execute the method, by default Obj.base.
        **kwargs : Unpack[IpylabKwgs]
            The keyword arguments to pass to the method.

        Returns
        -------
        Any
            The result of the method call.
        """
        return await self._obj_operation(obj, subpath, "executeMethod", {"args": args}, kwargs)

    async def get_property(self, subpath: str, *, obj=Obj.base, null_if_missing=False, **kwargs: Unpack[IpylabKwgs]):
        """Get a property from an object in the frontend.

        Parameters
        ----------
        subpath: str
            The path to the property to get, e.g. "foo.bar".
        obj: Obj
            The object to get the property from.
        null_if_missing: bool
            If True, return None if the property is missing.
        **kwargs: Unpack[IpylabKwgs]
            Keyword arguments to pass to the Javascript function.

        Returns
        -------
        Any
            The value of the property.
        """
        return await self._obj_operation(obj, subpath, "getProperty", {"null_if_missing": null_if_missing}, kwargs)

    async def set_property(self, subpath: str, value, *, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]) -> None:
        """Set a property of an object in the frontend.

        Args:
            subpath: The path to the property to set.
            value: The value to set the property to.
            obj: The JavaScript object to set the property on. Defaults to Obj.base.
            **kwargs: Keyword arguments to pass to the JavaScript function.

        Returns:
            None
        """
        return await self._obj_operation(obj, subpath, "setProperty", {"value": value}, kwargs)

    async def update_property(
        self, subpath: str, value: dict[str, Any], *, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]
    ) -> dict[str, Any]:
        """Update a property of an object in the frontend equivalent to a `dict.update` call.

        Args:
            subpath: The path to the property to update.
            value: A mapping of the items to override (existing non-mapped values remain).
            obj: The object to update. Defaults to Obj.base.
            **kwargs: Keyword arguments to pass to the _obj_operation method.

        Returns:
            The updated property.
        """
        return await self._obj_operation(obj, subpath, "updateProperty", {"value": value}, kwargs)

    async def list_properties(
        self, subpath="", *, obj=Obj.base, depth=3, skip_hidden=True, **kwargs: Unpack[IpylabKwgs]
    ) -> dict[str, Any]:
        """List properties of a given object in the frontend.

        Args:
            subpath (str, optional): Subpath to the object. Defaults to "".
            obj (Obj, optional): Object to list properties from. Defaults to Obj.base.
            depth (int, optional): Depth of the inheritance introspection on the object in the front. Defaults to 3.
            skip_hidden (bool, optional): Whether to skip hidden properties. Defaults to True.
            **kwargs (Unpack[IpylabKwgs]): Additional keyword arguments.

        Returns:
            dict[str, Any]: Dictionary of properties.
        """
        kwgs = {"depth": depth, "omitHidden": skip_hidden}
        return await self._obj_operation(obj, subpath, "listProperties", kwgs, kwargs)

    @classmethod
    def _list_signals(cls, obj, *, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "<signals>":
                    for signal in v:
                        yield f"{prefix}.{signal}".strip(".")
                elif isinstance(v, dict):
                    yield from cls._list_signals(v, prefix=f"{prefix}.{k}".strip("."))

    def register_signal_callback(
        self, dottedname: str, callback: Callable[[SignalCallbackData], None | CoroutineType], *, remove=False
    ):
        """Registers a callback function to be executed when a specific signal is emitted.

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

    async def list_signals(self, depth=3):
        """List the nested signals associated with the base in the frontend.

        See also:
        * `register_signal_callback`
        * `list_view_signals`
        """
        properties = await self.list_properties(depth=depth)
        return list(self._list_signals(properties))

    async def list_view_signals(self, depth=3):
        """List the nested signals belonging to a view of this object.

        Notes:
        * This only applies to widgets that have a view.
        * To list the signals in a view, at least one view of the object must be live.

        See also:
        * `register_signal_callback`
        * `list_signals`
        """
        if not (views := (await self.list_properties("views")).get("<promises>")):
            msg = f"No views found for {self}"
            raise ValueError(msg)
        properties = await self.list_properties(f"views[{views[0]}]", depth=depth)
        return list(dict.fromkeys(self._list_signals(properties, prefix="views")))
