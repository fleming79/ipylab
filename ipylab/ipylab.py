# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import uuid
import weakref
from typing import TYPE_CHECKING, Any, TypeVar

import traitlets
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
from ipylab.common import (
    Fixed,
    IpylabKwgs,
    Obj,
    TaskHooks,
    TaskHookType,
    Transform,
    TransformType,
    pack,
    trait_tuple_add,
)
from ipylab.log import IpylabLoggerAdapter

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Awaitable, Callable
    from typing import Self, Unpack


__all__ = ["Ipylab", "WidgetBase"]

T = TypeVar("T")
L = TypeVar("L", bound="Ipylab")


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

    Attributes:
        _model_name (Unicode): The name of the model.
        _python_class (Unicode): The name of the Python class.
        ipylab_base (IpylabBase): The base ipylab object.
        _ready (Bool): Whether the widget is ready.
        _on_ready_callbacks (List): A list of callbacks to execute when the widget is ready.
        _ready_event (asyncio.Event): An event that is set when the widget is ready.
        _comm: The comm object.
        _ipylab_init_complete (bool): Whether the ipylab initialization is complete.
        _pending_operations (Dict): A dictionary of pending operations.
        _has_attrs_mappings (Set): A set of attribute mappings.
        ipylab_tasks (Set): A set of ipylab tasks.
        close_extras (Fixed): A set of extra widgets to close.
        log (Instance): A logger instance.
        app (Fixed): A reference to the ipylab App instance.
    """

    _model_name = Unicode("IpylabModel", help="Name of the model.", read_only=True).tag(sync=True)
    _python_class = Unicode().tag(sync=True)
    ipylab_base = IpylabBase(Obj.this, "").tag(sync=True)
    _ready = Bool(read_only=True, help="Set to by frontend when ready").tag(sync=True)
    _on_ready_callbacks: Container[list[Callable[[], None | Awaitable] | Callable[[Self], None | Awaitable]]] = List(
        trait=traitlets.Callable()
    )
    _ready_event: asyncio.Event | None = None
    _comm = None
    _ipylab_init_complete = False
    _pending_operations: Dict[str, asyncio.Future] = Dict()
    _has_attrs_mappings: Container[set[tuple[HasTraits, str]]] = Set()
    ipylab_tasks: Container[set[asyncio.Task]] = Set()
    close_extras: Fixed[Self, weakref.WeakSet[Widget]] = Fixed(weakref.WeakSet)
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
        if change["name"] == "_ready":
            if self._ready:
                if self._ready_event:
                    self._ready_event.set()
                for cb in self._on_ready_callbacks:
                    self.ensure_run(cb)
            elif self._ready_event:
                self._ready_event.clear()

    def close(self):
        if self.comm:
            self._ipylab_send({"close": True})
        super().close()
        for task in self.ipylab_tasks:
            task.cancel()
        self.ipylab_tasks.clear()
        for item in list(self.close_extras):
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

    async def _wrap_awaitable(self, aw: Awaitable[T], hooks: TaskHookType) -> T:
        await self.ready()
        try:
            result = await aw
        except Exception:
            self.log.exception("Awaiting %s", aw, obj={"hooks": hooks, "aw": aw})
            raise
        else:
            if hooks:
                try:
                    self._task_result(result, hooks)
                except Exception:
                    self.log.exception("Running hooks", obj={"result": result, "hooks": hooks, "aw": aw})
                    raise
            return result

    def _task_result(self: Ipylab, result: Any, hooks: TaskHooks):
        # close with
        for owner in hooks.pop("close_with_fwd", ()):
            # Close result with each item.
            if isinstance(owner, Ipylab) and isinstance(result, Widget):
                if not owner.comm:
                    result.close()
                    raise RuntimeError(str(owner))
                owner.close_extras.add(result)
        for obj_ in hooks.pop("close_with_rev", ()):
            # Close each item with the result.
            if isinstance(result, Ipylab):
                result.close_extras.add(obj_)
        # tuple add
        for owner, name in hooks.pop("add_to_tuple_fwd", ()):
            # Add each item of to tuple of result.
            if isinstance(result, Ipylab):
                result.add_to_tuple(owner, name)
            else:
                trait_tuple_add(owner, name, result)
        for name, value in hooks.pop("add_to_tuple_rev", ()):
            # Add the result the the tuple with 'name' for each item.
            if isinstance(value, Ipylab):
                value.add_to_tuple(result, name)
            else:
                trait_tuple_add(result, name, value)
        # trait add
        for name, value in hooks.pop("trait_add_fwd", ()):
            # Set each trait of result with value.
            if isinstance(value, Ipylab):
                value.add_as_trait(result, name)
            else:
                result.set_trait(name, value)
        for owner, name in hooks.pop("trait_add_rev", ()):
            # Set set trait of each value with result.
            if isinstance(result, Ipylab):
                result.add_as_trait(owner, name)
            else:
                owner.set_trait(name, result)
        for cb in hooks.pop("callbacks", ()):
            self.ensure_run(cb(result))
        if hooks:
            msg = f"Invalid hooks detected: {hooks}"
            raise ValueError(msg)

    def _task_done_callback(self, task: Task):
        self.ipylab_tasks.discard(task)
        # TODO: It'd be great if we could cancel in the frontend.
        # Unfortunately it looks like Javascript Promises can't be cancelled.
        # https://stackoverflow.com/questions/30233302/promise-is-it-possible-to-force-cancel-a-promise#30235261

    def _on_custom_msg(self, _, msg: dict, buffers: list):
        content = msg.get("ipylab")
        if not content:
            return
        try:
            c = json.loads(content)
            if "ipylab_PY" in c:
                op = self._pending_operations.pop(c["ipylab_PY"])
                if "error" in c:
                    op.set_exception(self._to_frontend_error(c))
                else:
                    op.set_result(c.get("payload"))
            elif "ipylab_FE" in c:
                return self.to_task(self._do_operation_for_fe(c["ipylab_FE"], c["operation"], c["payload"], buffers))
            elif "closed" in c:
                self.close()
            else:
                raise NotImplementedError(msg)  # noqa: TRY301
        except Exception:
            self.log.exception("Message processing error", obj=msg)

    def _to_frontend_error(self, content):
        error = content["error"]
        operation = content.get("operation")
        if operation:
            msg = f'Operation "{operation}" failed with the message "{error}"'
            return IpylabFrontendError(msg)
        return IpylabFrontendError(error)

    async def _do_operation_for_fe(self, ipylab_FE: str, operation: str, payload: dict, buffers: list | None):
        """Handle operation requests from the frontend and reply with a result."""
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
        except Exception:
            self.log.exception("Operation for frontend error", obj={"operation": operation, "payload": payload})
        finally:
            self._ipylab_send(content, buffers)

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        """Perform an operation for a custom message with an ipylab_FE uuid."""
        raise NotImplementedError(operation)

    def _obj_operation(self, base: Obj, subpath: str, operation: str, kwgs, kwargs: IpylabKwgs):
        kwgs |= {"genericOperation": operation, "basename": base, "subpath": subpath}
        return self.operation("genericOperation", kwgs, **kwargs)

    def ensure_run(self, aw: Callable | Awaitable | None) -> None:
        """Ensure aw is run.

        Parameters
        ----------
        aw: Callable | Awaitable | None
            `aw` can be a function that accepts either no arguments or one keyword argument 'obj'.
        """
        try:
            if callable(aw):
                aw = aw(self) if len(inspect.signature(len).parameters) == 1 else aw()
            if inspect.iscoroutine(aw):
                self.to_task(aw, f"Ensure run {aw}")
        except Exception:
            self.log.exception("Ensure run", obj=aw)
            raise

    async def ready(self) -> Self:
        """Wait for the application to be ready.

        If this is not the main application instance, it waits for the
        main application instance to be ready first.
        """
        app = self.app
        if app is not self and not app._ready:  # noqa: SLF001
            await app.ready()
        if not self._ready:  # type: ignore
            if self._ready_event:
                try:
                    await self._ready_event.wait()
                    # Event.wait is pinned to the event loop in which Event was created.
                    # A Runtime error will occur when called from a different event loop.
                except RuntimeError:
                    pass
                else:
                    return self
            self._ready_event = asyncio.Event()
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

    def _ipylab_send(self, content, buffers: list | None = None):
        try:
            self.send({"ipylab": json.dumps(content, default=pack)}, buffers)
        except Exception:
            self.log.exception("Send error", obj=content)
            raise

    def to_task(self, aw: Awaitable[T], name: str | None = None, *, hooks: TaskHookType = None) -> Task[T]:
        """Run aw in an eager task.

        If the task is running when this object is closed the task will be cancel.
        Noting the corresponding promise in the frontend will run to completion.

        aw: An awaitable to run in the task.

        name: str
            The name of the task.

        hooks: TaskHookType

        """

        self._check_closed()
        task = asyncio.eager_task_factory(asyncio.get_running_loop(), self._wrap_awaitable(aw, hooks), name=name)
        if not task.done():
            self.ipylab_tasks.add(task)
            task.add_done_callback(self._task_done_callback)
        return task

    def operation(
        self,
        operation: str,
        kwgs: dict | None = None,
        *,
        transform: TransformType = Transform.auto,
        toLuminoWidget: list[str] | None = None,
        toObject: list[str] | None = None,
        hooks: TaskHookType = None,
    ) -> Task[Any]:
        """Create a new task requesting an operation to be performed in the frontend.

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

        hooks: TaskHookType
            see: TaskHooks
        """
        # validation
        self._check_closed()
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

        self._pending_operations[ipylab_PY] = op = asyncio.get_running_loop().create_future()

        async def _operation(content: dict):
            self._ipylab_send(content)
            payload = await op
            return Transform.transform_payload(content["transform"], payload)

        return self.to_task(_operation(content), name=ipylab_PY, hooks=hooks)

    def execute_method(self, subpath: str, *args, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "executeMethod", {"args": args}, kwargs)

    def get_property(self, subpath: str, *, obj=Obj.base, null_if_missing=False, **kwargs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "getProperty", {"null_if_missing": null_if_missing}, kwargs)

    def set_property(self, subpath: str, value, *, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "setProperty", {"value": value}, kwargs)

    def update_property(self, subpath: str, value: dict[str, Any], *, obj=Obj.base, **kwargs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "updateProperty", {"value": value}, kwargs)

    def list_properties(
        self, subpath="", *, obj=Obj.base, depth=3, skip_hidden=True, **kwargs: Unpack[IpylabKwgs]
    ) -> Task[dict]:
        return self._obj_operation(obj, subpath, "listProperties", {"depth": depth, "omitHidden": skip_hidden}, kwargs)
