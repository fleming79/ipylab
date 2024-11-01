# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
import typing
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict

import pluggy
from ipywidgets import Widget, widget_serialization

import ipylab

__all__ = ["Area", "Obj", "InsertMode", "Transform", "TransformType", "hookimpl", "pack", "IpylabKwgs"]

hookimpl = pluggy.HookimplMarker("ipylab")  # Used for plugins

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import TypeVar, overload

    from traitlets import HasTraits

    from ipylab.ipylab import Ipylab

    T = TypeVar("T")

    @overload
    def pack(obj: Widget) -> str: ...
    @overload
    def pack(obj: inspect._SourceObjectType) -> str: ...  # Technically only modules and functions.
    @overload
    def pack(obj: T) -> T: ...


def pack(obj):
    "Return serialized obj if it is a Widget or string if code else passes through."

    if isinstance(obj, Widget):
        return widget_serialization["to_json"](obj, None)
    if inspect.isfunction(obj) or inspect.ismodule(obj):
        return inspect.getsource(obj)
    return obj


class Obj(StrEnum):
    "The objects available to use as 'obj' in the Frontend."

    this = "this"
    base = "base"
    # These provides static access to the class
    IpylabModel = "IpylabModel"
    MainMenu = "MainMenu"


class Area(StrEnum):
    # https://github.com/jupyterlab/jupyterlab/blob/da8e7bda5eebd22319f59e5abbaaa9917872a7e8/packages/application/src/shell.ts#L500
    main = "main"
    left = "left"
    right = "right"
    header = "header"
    top = "top"
    bottom = "bottom"
    down = "down"
    menu = "menu"


class InsertMode(StrEnum):
    # ref https://lumino.readthedocs.io/en/latest/api/types/widgets.DockLayout.InsertMode.html
    split_top = "split-top"
    split_left = "split-left"
    split_right = "split-right"
    split_bottom = "split-bottom"
    merge_top = "merge-top"
    merge_left = "merge-left"
    merge_right = "merge-right"
    merge_bottom = "merge-bottom"
    tab_before = "tab-before"
    tab_after = "tab-after"


class ErrorSource(StrEnum):
    FrontendError = "Frontend error"
    TaskError = "Task error"
    SendError = "Send error"
    MessageError = "Message processing error"
    OperationForFrontendError = "Operation for frontend error"
    EnsureRun = "Ensure run"


class Transform(StrEnum):
    """An eumeration of transformations to apply to the result of an operation
    performed on the Frontend prior to returning to Python and transformation
    of the result in python.

    Transformations that require parameters can be specified as dict with the key `transform`.

    - auto: [default] Raw data or a connection.
    - connection: Return a connection to a disposable object in the frontend.
    - function: Use a function to calculate the return value. ['code'] = 'function...'
    - advanced: A mapping of keys to transformations to apply sequentially on the object.

    `function`
    --------
    JS code defining a function and the data to return.

    The function must accept two args: obj, options.

    ```
    transform = {
        "transform": Transform.function,
        "code": "function (obj, options) { return obj.id; }",
    }

    transform = {
        "transform": Transform.connection,
        "cid": "ID TO USE FOR CONNECTION",
    }

    `advanced`
    ---------
    ```
    transform = {
    "transform": Transform.advanced,
    "mappings":  {path: TransformType, ...}
    }
    ```
    """

    auto = "auto"
    null = "null"
    function = "function"
    connection = "connection"
    advanced = "advanced"

    @classmethod
    def validate(cls, transform: TransformType):
        """Return a valid copy of the transform."""
        if isinstance(transform, dict):
            match cls(transform["transform"]):
                case cls.function:
                    code = transform.get("code")
                    if not isinstance(code, str) or not code.startswith("function"):
                        raise TypeError
                    return TransformDictFunction(transform=Transform.function, code=code)
                case cls.connection:
                    cid = transform.get("cid")
                    if cid and not cid.startswith(ipylab.Connection._PREFIX):  # noqa: SLF001
                        msg = f"'cid' should start with '{ipylab.Connection._PREFIX}' but got {cid=}"  # noqa: SLF001
                        raise ValueError(msg)
                    return TransformDictConnection(transform=Transform.connection, cid=cid)
                case cls.advanced:
                    mappings = {}
                    transform_ = TransformDictAdvanced(transform=Transform.advanced, mappings=mappings)
                    mappings_ = transform.get("mappings")
                    if not isinstance(mappings_, dict):
                        raise TypeError
                    for pth, tfm in mappings_.items():
                        mappings[pth] = cls.validate(tfm)
                    return transform_
                case _:
                    raise NotImplementedError
        transform_ = Transform(transform)
        if transform_ in [Transform.function, Transform.advanced]:
            msg = "This type of transform should be passed as a dict to provide the additional arguments"
            raise ValueError(msg)
        return transform_

    @classmethod
    def transform_payload(cls, transform: TransformType, payload):
        """Transform the payload according to the transform."""
        transform_ = transform["transform"] if isinstance(transform, dict) else transform
        match transform_:
            case Transform.advanced:
                mappings = typing.cast(TransformDictAdvanced, transform)["mappings"]
                return {key: cls.transform_payload(mappings[key], payload[key]) for key in mappings}
            case Transform.connection | Transform.auto if isinstance(payload, dict) and (cid := payload.get("cid")):
                conn = ipylab.Connection(cid)
                conn._check_closed()  # noqa: SLF001
                return conn
        return payload


class NotificationType(StrEnum):
    info = "info"
    progress = "in-progress"
    success = "success"
    warning = "warning"
    error = "error"
    default = "default"


class TransformDictFunction(TypedDict):
    transform: Literal[Transform.function]
    code: str


class TransformDictAdvanced(TypedDict):
    transform: Literal[Transform.advanced]
    mappings: dict[str, TransformType]


class TransformDictConnection(TypedDict):
    transform: Literal[Transform.connection]
    cid: NotRequired[str | None]


TransformType = Transform | TransformDictAdvanced | TransformDictFunction | TransformDictConnection


class IpylabKwgs(TypedDict):
    transform: NotRequired[TransformType]
    toLuminoWidget: NotRequired[list[str]]
    toObject: NotRequired[list[str]]
    hooks: NotRequired[TaskHookType]


class TaskHooks(TypedDict):
    """Hooks to run after successful completion of 'aw' passed to the method "to_task"
    and prior to returning.

    This provides a convenient means to set traits of the returned result.

    see: `Hookspec.task_result`
    """

    close_with_fwd: NotRequired[list[Ipylab]]  # result is closed when any item in list is closed
    close_with_rev: NotRequired[list[Widget]]  #

    trait_add_fwd: NotRequired[list[tuple[str, Any]]]
    trait_add_rev: NotRequired[list[tuple[HasTraits, str]]]

    add_to_tuple_fwd: NotRequired[list[tuple[HasTraits, str]]]
    add_to_tuple_rev: NotRequired[list[tuple[str, Ipylab]]]

    callbacks: NotRequired[list[Callable[[Any], None | Awaitable[None]]]]


TaskHookType = TaskHooks | None
