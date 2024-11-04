# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import traceback
import uuid
import weakref
from typing import TYPE_CHECKING, Any, TypeVar

from ipywidgets import Widget, register
from traitlets import Bool, Container, Dict, HasTraits, Instance, Set, TraitError, TraitType, Unicode, default, observe

import ipylab
import ipylab._frontend as _fe
from ipylab.common import ErrorSource, IpylabKwgs, Obj, TaskHookType, Transform, TransformType, pack
from ipylab.log import LogPayloadType, LogTypes

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Awaitable, Callable, Hashable
    from typing import ClassVar, Self, Unpack


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
    _ready_event = Instance(asyncio.Event, ())
    _comm = None

    _pending_operations: Dict[str, Response] = Dict()
    _tasks: Container[set[asyncio.Task]] = Set()
    _has_attrs_mappings: Container[set[tuple[HasTraits, str]]] = Set()
    close_extras: Container[weakref.WeakSet[Widget]] = Instance(weakref.WeakSet, (), help="extra items to close")  # type: ignore
    log = Instance(logging.Logger)

    @classmethod
    def _single_key(cls, kwgs: dict) -> Hashable:  # noqa: ARG003
        """The key used for finding instances when SINGLE is enabled."""
        return cls

    @property
    def hook(self):
        return ipylab.plugin_manager.hook

    @property
    def repr_info(self) -> dict[str, Any] | str:
        "Extra info to provide for __repr__."
        return {}

    @default("log")
    def _default_log(self):
        return ipylab.app.log

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

    async def __aenter__(self):
        if not self._ready:
            self._check_closed()
            await self.ready()
        self._check_closed()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    @observe("comm", "_ready")
    def _observe_comm(self, change: dict):
        if not self.comm:
            for task in self._tasks:
                task.cancel()
            self._tasks.clear()
            for item in self.close_extras:
                item.close()
            for obj, name in self._has_attrs_mappings:
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
                for cb in self.hook.ready(obj=self):
                    self.hook.ensure_run(obj=self, aw=cb)
                for cb in self._on_ready_callbacks:
                    self.hook.ensure_run(obj=self, aw=cb)

            else:
                self._ready_event.clear()

    def _check_closed(self):
        if not self._repr_mimebundle_:
            msg = f"This widget is closed {self!r}"
            raise RuntimeError(msg)

    async def _wrap_awaitable(self, aw: Awaitable[T], hooks: TaskHookType) -> T:
        try:
            async with self:
                if not hooks:
                    return await aw
                result = await aw
                try:
                    self.hook.task_result(obj=self, aw=aw, result=result, hooks=hooks)
                except Exception as e:
                    self.on_error(ErrorSource.TaskError, e)
                    raise e from None
                return result
        except Exception as e:
            try:
                self.on_error(ErrorSource.TaskError, e)
            finally:
                raise e

    def _task_done_callback(self, task: Task):
        self._tasks.discard(task)
        # TODO: It'd be great if we could cancel in the frontend.
        # Unfortunately it looks like Javascript Promises can't be cancelled.
        # https://stackoverflow.com/questions/30233302/promise-is-it-possible-to-force-cancel-a-promise#30235261

    def _to_error(self, content: dict) -> IpylabFrontendError | None:
        error = content["error"]
        operation = content.get("operation")
        if operation:
            msg = (
                f'{self.__class__.__name__} operation "{operation}" failed with message "{error}"'
                "\nNote: Additional information may be available in the browser console (press `F12`)"
            )
            return IpylabFrontendError(msg)
        return IpylabFrontendError(f'{self.__class__.__name__} failed with message "{error}"')

    def _on_custom_msg(self, _, msg: str, buffers: list):
        if not isinstance(msg, str):
            return
        try:
            content = json.loads(msg)
            error = self._to_error(content) if "error" in content else None
            if "operation" in content:
                if "ipylab_PY" in content:
                    self._pending_operations.pop(content["ipylab_PY"]).set(content.get("payload"), error)
                elif "ipylab_FE" in content:
                    self.to_task(self._do_operation_for_fe(buffers=buffers, **content))
            elif "closed" in content:
                self.close()
            if error:
                self.on_error(ErrorSource.FrontendError, error)
        except Exception as e:
            self.on_error(ErrorSource.MessageError, e)
            raise e from None

    async def _do_operation_for_fe(self, *, ipylab_FE: str, operation: str, payload: dict, buffers: list):
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
        except Exception as e:
            content["error"] = {
                "repr": repr(e).replace("'", '"'),
                "traceback": traceback.format_tb(e.__traceback__),
            }
            self.on_error(ErrorSource.OperationForFrontendError, e)
        finally:
            self.send(content, buffers)

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        """Perform an operation for a custom message with an ipylab_FE uuid."""
        raise NotImplementedError(operation)

    def _obj_operation(self, base: Obj, subpath: str, operation: str, ipl_kwgs: IpylabKwgs, **kwgs):
        return self.operation(
            "genericOperation", genericOperation=operation, basename=base, subpath=subpath, **ipl_kwgs, **kwgs
        )

    def close(self):
        self.send({"close": True})
        super().close()

    async def ready(self):
        await ipylab.app.ready()
        await self._ready_event.wait()

    def on_ready(self, callback, remove=False):  # noqa: FBT002
        if remove:
            self._on_ready_callbacks.discard(callback)
        else:
            self._on_ready_callbacks.add(callback)

    def on_error(self, source: ErrorSource, error: Exception):
        self.hook.on_error(obj=self, source=source, error=error)

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
        except Exception as e:
            self.on_error(ErrorSource.SendError, e)
            raise e from None

    def send_log_message(self, log: LogPayloadType):
        self.send({"log": LogTypes.parse(log)})

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
        *,
        transform: TransformType = Transform.auto,
        toLuminoWidget: list[str] | None = None,
        toObject: list[str] | None = None,
        hooks: TaskHookType = None,
        **kwgs,
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
            "kwgs": kwgs,
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

    def execute_method(self, subpath: str, *args, obj=Obj.base, **kwgs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "executeMethod", kwgs, args=args)

    def get_property(self, subpath: str, *, obj=Obj.base, null_if_missing=False, **kwgs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "getProperty", kwgs, null_if_missing=null_if_missing)

    def set_property(self, subpath: str, value, *, obj=Obj.base, **kwgs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "setProperty", kwgs, value=value)

    def update_property(self, subpath: str, value: dict[str, Any], *, obj=Obj.base, **kwgs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "updateProperty", kwgs, value=value)

    def list_properties(
        self, subpath="", *, obj=Obj.base, depth=3, skip_hidden=True, **kwgs: Unpack[IpylabKwgs]
    ) -> Task[dict]:
        return self._obj_operation(obj, subpath, "listProperties", kwgs, depth=depth, omitHidden=skip_hidden)
