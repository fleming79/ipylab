# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

import asyncio
import json
import traceback
import uuid
import weakref
from typing import TYPE_CHECKING, Any, TypeVar, Unpack

from ipywidgets import Widget, register
from traitlets import Bool, Container, Dict, HasTraits, Instance, Set, TraitType, Unicode, observe

import ipylab._frontend as _fe
from ipylab.common import IpylabKwgs, Obj, TaskHooks, TaskHookType, Transform, TransformType, hookimpl, pack

if TYPE_CHECKING:
    import logging
    from asyncio import Task
    from collections.abc import Awaitable, Hashable, Iterable
    from typing import ClassVar

    from ipylab import App
    from ipylab._compat.typing import Self


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
    app: Instance[App] = Instance("ipylab.App", (), read_only=True)


@register
class Ipylab(WidgetBase):
    """The base class for Ipylab which has a corresponding Frontend."""

    SINGLE = False

    _model_name = Unicode("IpylabModel", help="Name of the model.", read_only=True).tag(sync=True)
    _python_class = Unicode().tag(sync=True)
    ipylab_base = IpylabBase(Obj.this, "").tag(sync=True)

    _async_widget_base_init_complete = False
    _single_map: ClassVar[dict[Hashable, str]] = {}  # single_key : model_id
    _single_models: ClassVar[dict[str, Self]] = {}  #  model_id   : Widget
    _ready_event = Instance(asyncio.Event, ())
    _comm = None

    _pending_operations: Dict[str, Response] = Dict()
    _tasks: Container[set[asyncio.Task]] = Set()
    _has_attrs_mappings: Container[set[tuple[HasTraits, str]]] = Set()
    close_extras: Container[weakref.WeakSet[Widget]] = Instance(weakref.WeakSet, (), help="extra items to close")  # type: ignore
    ready = Bool(read_only=True, help="Set to True when `init` message received")
    if TYPE_CHECKING:
        log: logging.Logger

    @classmethod
    def _single_key(cls, kwgs: dict) -> Hashable:  # noqa: ARG003
        """The key used for finding instances when SINGLE is enabled."""
        return cls

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
        elif (not self.ready) and self._repr_mimebundle_:
            status = "Not ready"
        else:
            status = ""
        info = ", ".join(f"{k}={v!r}" for k, v in self.rep_info.items())
        if status:
            return f"< {status}: {self.__class__.__name__}({info}) >"
        return f"{status}{self.__class__.__name__}({info})"

    async def __aenter__(self):
        if not self.ready:
            self._check_closed()
            await self._ready_event.wait()
        self._check_closed()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    @observe("comm")
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
                        obj.set_trait(name, None)
                    elif isinstance(val, tuple):
                        obj.set_trait(name, tuple(v for v in val if v.comm))
            if self.SINGLE:
                self._single_models.pop(change["old"].id)

    def close(self):
        self.send({"close": True})
        super().close()

    def _check_closed(self):
        if not self._repr_mimebundle_:
            msg = f"This widget is closed {self!r}"
            raise RuntimeError(msg)

    def add_to_tuple(self, name: str, obj: HasTraits):
        """Add self to the tuple of obj."""

        items = getattr(obj, name)
        if self.comm and self not in items:
            obj.set_trait(name, (*items, self))
        # see: _observe_comm for removal
        self._has_attrs_mappings.add((obj, name))

    def add_as_trait(self, name: str, obj: HasTraits):
        "Add self as a trait to obj."
        self._check_closed()
        obj.set_trait(name, self)
        # see: _observe_comm for removal
        self._has_attrs_mappings.add((obj, name))

    @property
    def hook(self):
        return self.app.plugin_manager.hook

    @property
    def rep_info(self) -> dict[str, Any]:
        "Extra info to provide for __repr__."
        return {}

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

    async def _wrap_awaitable(self, aw: Awaitable[T], hooks: TaskHookType) -> T:
        try:
            async with self:
                if not hooks:
                    return await aw
                result = await aw
                try:
                    self.hook.task_result(obj=self, aw=aw, result=result, hooks=hooks)
                except Exception as e:
                    self.hook.on_task_error(obj=self, aw=aw, error=e)
                return result
        except Exception as e:
            try:
                self.hook.on_task_error(obj=self, aw=aw, error=e)
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

    def send(self, content, buffers=None):
        try:
            super().send(json.dumps(content, default=pack), buffers)
        except Exception as error:
            self.hook.on_send_error(obj=self, error=error, content=content, buffers=buffers)

    async def _send_receive(self, content: dict):
        async with self:
            self._pending_operations[content["ipylab_PY"]] = response = Response()
            self.send(content)
            try:
                return await self._wait_response_check_error(response, content)
            except asyncio.CancelledError:
                if not self.comm:
                    msg = f"This widget is closed {self!r}"
                    raise asyncio.CancelledError(msg) from None
                raise

    async def _wait_response_check_error(self, response: Response, content: dict) -> Any:
        payload = await response.wait()
        return await Transform.transform_payload(content["transform"], payload)

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
            elif "init" in content:
                match content["init"]:
                    case "ipylabInit":
                        self._ready_event.clear()
                        self.set_trait("ready", False)
                    case "ready":
                        self._ready_event.set()
                        self.set_trait("ready", True)
                        self.on_frontend_init()
            elif "closed" in content:
                self.close()
            if error:
                self.hook.on_frontend_error(obj=self, error=error, content=content, buffers=buffers)
        except Exception as e:
            self.hook.on_message_error(obj=self, error=e, msg=msg, buffers=buffers)

    def on_frontend_init(self):
        """Called when the frontend is initialized.

        This will occur on initial connection and whenever the model is restored from the kernel.

        The 'ready' trait offers a similar callback functionality using traits instead."""

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
            self.hook.on_do_operation_for_fe_error(obj=self, error=e, content=content, buffers=buffers)
        finally:
            self.send(content, buffers)

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        """Perform an operation for a custom message with an ipylab_FE uuid."""
        raise NotImplementedError(operation)

    def operation(
        self,
        operation: str,
        *,
        transform: TransformType = Transform.auto,
        toLuminoWidget: Iterable[str] | None = None,
        toObject: Iterable[str] = (),
        hooks: TaskHookType = None,
        **kwgs,
    ):
        """Create a new task requesting an operation to be performed in the frontend.

        operation: str
            Name corresponding to operation in JS frontend.

        transform : Transform | dict
            The transform to apply to the result of the operation.
            see: ipylab.Transform

        toLuminoWidget: Iterable[str] | None
            A list of item name mappings to convert to a Lumino widget in the frontend.
            Each string should correspond to the dotted subpath/index in kwgs that has
            the packed (json version of the widget or id of a lumino widget)

        toObject:  Iterable[str] | None
            A list of item name mappings in the .

            ```
            Examples:
            --------

            ```python
            kwgs = {"widget": "IPY_MODEL_<UUID>", "options": {"ref": "IPY_MODEL_<UUID>"}}
            toLuminoWidget = ["widget", "options.ref"]

            kwgs = {
                "args": [
                    "IPY_MODEL_<UUID>",
                    1,
                    "dotted.attribute.name",
                    "IPY_MODEL_<UUID>.value",
                ]
            }
            toLuminoWidget = ["args[0]", "kwgs.options.ref"]
            toObject = ["args[2]", "args[3]"]
        basename: Base | None
            specify the 'obj' to use in the fronted.
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
            content["toLuminoWidget"] = list(map(str, toLuminoWidget))
        if toObject:
            content["toObject"] = list(map(str, toObject))

        return self.to_task(self._send_receive(content), name=ipylab_PY, hooks=hooks)

    def _obj_operation(self, base: Obj, subpath: str, operation: str, args: tuple, **kwgs: Unpack[IpylabKwgs]):
        return self.operation(
            "genericOperation", genericOperation=operation, basename=base, subpath=subpath, args=args, **kwgs
        )

    def execute_method(self, subpath: str, *args, obj=Obj.base, **kwgs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "executeMethod", args, **kwgs)

    def get_property(self, subpath: str, *, obj=Obj.base, null_if_missing=False, **kwgs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "getProperty", (null_if_missing,), **kwgs)

    def set_property(self, subpath: str, value, *, obj=Obj.base, **kwgs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "setProperty", value, **kwgs)

    def update_property(self, subpath: str, value: dict, *, obj=Obj.base, **kwgs: Unpack[IpylabKwgs]):
        return self._obj_operation(obj, subpath, "updateProperty", (value,), **kwgs)

    def list_properties(
        self, subpath="", *, obj=Obj.base, depth=3, skip_hidden=True, **kwgs: Unpack[IpylabKwgs]
    ) -> Task[dict]:
        args = ({"depth": depth, "omitHidden": skip_hidden},)
        return self._obj_operation(obj, subpath, "listProperties", args, **kwgs)


class IpylabPlugin:
    def handle_error(self, obj: Ipylab, title, msg):
        obj.log.error(msg)
        obj.app.dialog.show_error_message(title, msg)

    @hookimpl
    def on_frontend_error(self, obj: Ipylab, error: Exception, content: dict, buffers) -> None:  # noqa: ARG002
        self.handle_error(obj, "Frontend error", f"{error=} {obj=}")

    @hookimpl
    def on_send_error(self, obj: Ipylab, error: Exception, content: dict, buffers) -> None:  # noqa: ARG002
        self.handle_error(obj, "Send error", f"{error=} {obj=}")

    @hookimpl
    def unhandled_frontend_operation_message(self, obj: Ipylab, operation: str):
        self.handle_error(obj, "Unhandled frontend message", f"The {operation=} is unhandled for {obj} ")

    @hookimpl
    def on_do_operation_for_fe_error(self, obj: Ipylab, error: Exception, content: dict, buffers):  # noqa: ARG002
        self.handle_error(obj, "Error performing operation for frontend", str(error))

    @hookimpl
    def on_task_error(self, obj: Ipylab, aw: str, error: Exception) -> None:  # noqa: ARG002
        self.handle_error(obj, "Task error", str(error))

    @hookimpl
    def on_message_error(self, obj: Ipylab, msg: str, error: Exception) -> None:
        self.handle_error(obj, "Message error", f"{error=}\n{obj=}\n{msg=}'")

    @hookimpl
    def task_result(self, obj: Ipylab, result: HasTraits, hooks: TaskHooks):  # noqa: ARG002
        # close with
        for item in hooks.pop("close_with_fwd", ()):
            if isinstance(result, Ipylab):
                result.close_extras.add(item)
        for item in hooks.pop("close_with_rev", ()):
            if isinstance(result, Widget):
                item.close_extras.add(result)

        # tuple add
        for name, value in hooks.pop("tuple_add_fwd", ()):
            value.add_to_tuple(name, result)
        for name, value in hooks.pop("tuple_add_rev", ()):
            if isinstance(result, Ipylab):
                result.add_to_tuple(name, value)

        # trait add
        for name, value in hooks.pop("trait_add_fwd", ()):
            if isinstance(value, Ipylab):
                value.add_as_trait(name, result)
            else:
                result.set_trait(name, value)
        for name, value in hooks.pop("trait_add_rev_", ()):
            if isinstance(result, Ipylab):
                result.add_as_trait(name, value)
            else:
                value.set_trait(name, result)

        if hooks:
            msg = f"Invalid hooks detected: {hooks}"
            raise ValueError(msg)

    @hookimpl
    def opening_console(self, app: App, args: dict, objects: dict, kwgs: IpylabKwgs):
        "no-op"

    @hookimpl
    def vpath_getter(self, app: App, kwgs: dict) -> Awaitable[str] | str:
        return app.dialog.get_text(**kwgs)
