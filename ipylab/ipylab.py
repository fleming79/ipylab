# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import uuid
import weakref
from typing import TYPE_CHECKING, Any, Generic, TypedDict, TypeVar

from ipywidgets import Widget, register
from traitlets import Bool, Container, Dict, HasTraits, Instance, Set, TraitError, TraitType, Unicode, default, observe

import ipylab
import ipylab._frontend as _fe
from ipylab.common import IpylabKwgs, Obj, TaskHooks, TaskHookType, Transform, TransformType, pack, trait_tuple_add
from ipylab.log import IpylabLoggerAdapter

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Awaitable, Callable, Hashable
    from typing import ClassVar, Self, Unpack


__all__ = ["Ipylab", "WidgetBase", "Readonly", "ReadonlyCreated"]

T = TypeVar("T")
L = TypeVar("L", bound="Ipylab")


class IpylabBase(TraitType[tuple[str, str], None]):
    info_text = "A mapping to the base in the frontend."
    read_only = True

    def __init__(self, base: Obj, subpath: str):
        "The 'mapping' to the 'base' in the frontend."
        self._trait = Unicode()
        super().__init__((base, subpath))


class ReadonlyCreated(Generic[T], TypedDict):
    name: str
    obj: T
    owner: Any


class Readonly(Generic[T]):
    __slots__ = ["name", "instances", "klass", "args", "kwgs", "dynamic", "created"]

    def __init__(
        self,
        klass: type[T],
        *args,
        dynamic: list[str] | None = None,
        created: Callable[[ReadonlyCreated[T]]] | str = "",
        **kwgs,
    ):
        """Define an instance of `klass` as a cached read only property.
        `args` and `kwgs` are used to instantiate `klass`.

        Parameters:
        ----------

        dynamic: list[str]:
            A list of argument names to call during creation. It is called with obj (owner)
            as an argument.

        created: Callable[ReadonlyCreatedDict] | str
            A function to call when the instance is created.
            If it is a non-empty string, it will call the method on the `owner` with that name.

        **kwgs:
            `kwgs` to pass when instantiating `klass`. Arguments listed in dynamic
            are first called with obj as an argument to obtain the value to
            substitute in place of the dynamic function.
        """
        if callable(created) and len(inspect.signature(created).parameters) != 1:
            msg = "'created' must be a callable the accepts two arguments."
            raise ValueError(msg)
        if dynamic:
            for k in dynamic:
                if not callable(kwgs[k]) or len(inspect.signature(kwgs[k]).parameters) != 1:
                    msg = f"Argument'{k}' must a callable that accepts one argument."
                    raise ValueError(msg)
        self.created = created
        self.dynamic = dynamic
        self.args = args
        self.klass = klass
        self.kwgs = kwgs
        self.instances = weakref.WeakKeyDictionary()

    def __set_name__(self, owner_cls, name: str):
        self.name = name

    def __get__(self, obj, objtype=None) -> T:
        if obj is None:
            return self  # type: ignore
        if obj not in self.instances:
            kwgs = self.kwgs
            if self.dynamic:
                kwgs = kwgs.copy()
                for k in self.dynamic:
                    kwgs[k] = kwgs[k](obj)
            self.instances[obj] = self.klass(*self.args, **kwgs)
            try:
                if self.created:
                    created = getattr(obj, self.created) if isinstance(self.created, str) else self.created
                    created(ReadonlyCreated(owner=obj, obj=self.instances[obj], name=self.name))
            except Exception:
                if log := getattr(obj, "log", None):
                    log.exception("Callback `created` failed", obj=self.created)
        return self.instances[obj]

    def __set__(self, obj, value):
        msg = f"Setting {obj.__class__.__name__}.{self.name} is forbidden!"
        raise AttributeError(msg)


class Response(asyncio.Event):
    def set(self, payload, error: Exception | None = None) -> None:
        if getattr(self, "_value", False):
            msg = "Already set!"
            raise RuntimeError(msg)
        self.payload = payload
        self.error = error
        super().set()

    async def wait(self) -> Any:
        """Wait for a message and return the response."""
        await super().wait()
        if self.error:
            raise self.error
        return self.payload


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
    """The base class for Ipylab which has a corresponding Frontend."""

    SINGLE = False

    _model_name = Unicode("IpylabModel", help="Name of the model.", read_only=True).tag(sync=True)
    _python_class = Unicode().tag(sync=True)
    ipylab_base = IpylabBase(Obj.this, "").tag(sync=True)
    _ready = Bool(read_only=True, help="Set to by frontend when ready").tag(sync=True)

    _on_ready_callbacks: Container[set[Callable]] = Set()

    _async_widget_base_init_complete = False
    _single_map: ClassVar[dict[Hashable, str]] = {}  # single_key : model_id
    _single_models: ClassVar[dict[str, Self]] = {}  #  model_id   : Widget
    _ready_event = Readonly(asyncio.Event)
    _comm = None

    _pending_operations: Dict[str, Response] = Dict()
    _tasks: Container[set[asyncio.Task]] = Set()
    _has_attrs_mappings: Container[set[tuple[HasTraits, str]]] = Set()
    close_extras: Readonly[weakref.WeakSet[Widget]] = Readonly(weakref.WeakSet)
    log = Instance(IpylabLoggerAdapter, read_only=True)

    @classmethod
    def _single_key(cls, kwgs: dict) -> Hashable:  # noqa: ARG003
        """The key used for finding instances when SINGLE is enabled."""
        return cls

    @property
    def repr_info(self) -> dict[str, Any] | str:
        "Extra info to provide for __repr__."
        return {}

    @default("log")
    def _default_log(self):
        return IpylabLoggerAdapter("ipylab", owner=self)

    def __new__(cls, **kwgs) -> Self:
        model_id = kwgs.get("model_id") or cls._single_map.get(cls._single_key(kwgs)) if cls.SINGLE else None
        if model_id and model_id in cls._single_models:
            return cls._single_models[model_id]
        return super().__new__(cls)

    def __init__(self, **kwgs):
        if self._async_widget_base_init_complete:
            return
        # set traits, including read only traits.
        model_id = kwgs.pop("model_id", None)
        for k in kwgs:
            if self.has_trait(k):
                self.set_trait(k, kwgs[k])
        self.set_trait("_python_class", self.__class__.__name__)
        super().__init__(model_id=model_id) if model_id else super().__init__()
        model_id = self.model_id
        if not model_id:
            msg = "Failed to init comms"
            raise RuntimeError(msg)
        if key := self._single_key(kwgs) if self.SINGLE else None:
            self._single_map[key] = model_id
            self._single_models[model_id] = self
        self.on_msg(self._on_custom_msg)
        self._async_widget_base_init_complete = True

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
            for task in self._tasks:
                task.cancel()
            self._tasks.clear()
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
            if self.SINGLE:
                self._single_models.pop(change["old"].comm_id, None)  # type: ignore
        if change["name"] == "_ready":
            if self._ready:
                self._ready_event.set()
                for cb in ipylab.plugin_manager.hook.ready(obj=self):
                    self.ensure_run(cb)
                for cb in self._on_ready_callbacks:
                    self.ensure_run(cb)

            else:
                self._ready_event.clear()

    def _check_closed(self):
        if not self._repr_mimebundle_:
            msg = f"This widget is closed {self!r}"
            raise RuntimeError(msg)

    async def _wrap_awaitable(self, aw: Awaitable[T], hooks: TaskHookType) -> T:
        await self.ready()
        try:
            if not hooks:
                return await aw
            result = await aw
            try:
                self._task_result(result, hooks)
            except Exception:
                self.log.exception("TaskHook error", obj={"result": result, "hooks": hooks, "aw": aw})
                raise
        except Exception:
            self.log.exception("Task error", obj=aw)
            raise
        else:
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
        self._tasks.discard(task)
        # TODO: It'd be great if we could cancel in the frontend.
        # Unfortunately it looks like Javascript Promises can't be cancelled.
        # https://stackoverflow.com/questions/30233302/promise-is-it-possible-to-force-cancel-a-promise#30235261

    def _on_custom_msg(self, _, msg: str, buffers: list):
        if not isinstance(msg, str):
            return
        try:
            c = json.loads(msg)
            if "ipylab_PY" in c:
                error = self._to_frontend_error(c) if "error" in c else None
                self._pending_operations.pop(c["ipylab_PY"]).set(c.get("payload"), error)
            elif "ipylab_FE" in c:
                self.to_task(self._do_operation_for_fe(c["ipylab_FE"], c["operation"], c["payload"], buffers))
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

    async def _do_operation_for_fe(self, ipylab_FE: str, operation: str, payload: dict, buffers: list):
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
            self.send(content, buffers)

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        """Perform an operation for a custom message with an ipylab_FE uuid."""
        raise NotImplementedError(operation)

    def _obj_operation(self, base: Obj, subpath: str, operation: str, kwgs, kwargs: IpylabKwgs):
        kwgs |= {"genericOperation": operation, "basename": base, "subpath": subpath}
        return self.operation("genericOperation", kwgs, **kwargs)

    def close(self):
        self.send({"close": True})
        super().close()

    def ensure_run(self, aw: Callable | Awaitable | None) -> None:
        """Ensure the aw is run.

        aw: Callable | Awaitable | None
            `aw` can be a function that accepts either no arguments or one keyword argument 'obj'.
        """
        try:
            if callable(aw):
                try:
                    aw = aw(self)
                except TypeError:
                    aw = aw()
            if inspect.iscoroutine(aw):
                self.to_task(aw, f"Ensure run {aw}")
        except Exception:
            self.log.exception("Ensure run", obj=aw)
            raise

    async def ready(self):
        if not ipylab.app._ready_event._value:  # type: ignore # noqa: SLF001
            await ipylab.app.ready()
        if not self._ready_event._value:  # type: ignore  # noqa: SLF001
            await self._ready_event.wait()

    def on_ready(self, callback, remove=False):  # noqa: FBT002
        if remove:
            self._on_ready_callbacks.discard(callback)
        else:
            self._on_ready_callbacks.add(callback)

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

    def send(self, content, buffers=None):
        try:
            super().send(json.dumps(content, default=pack), buffers)
        except Exception:
            self.log.exception("Send error", obj=content)
            raise

    def to_task(self, aw: Awaitable[T], name: str | None = None, *, hooks: TaskHookType = None) -> Task[T]:
        """Run aw in a task.

        If the task is running when this object is closed the task will be cancel.
        Noting the corresponding promise in the frontend will run to completion.

        aw: An awaitable to run in the task.

        name: str
            The name of the task.

        hooks: TaskHookType

        """

        self._check_closed()
        task = asyncio.create_task(self._wrap_awaitable(aw, hooks), name=name)
        self._tasks.add(task)
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

        self._pending_operations[ipylab_PY] = response = Response()

        async def _operation(content: dict):
            self.send(content)
            payload = await response.wait()
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
