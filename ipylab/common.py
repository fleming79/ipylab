from __future__ import annotations

import inspect
import typing
from typing import TYPE_CHECKING, Any, Literal

import pluggy
from ipywidgets import Widget, widget_serialization

import ipylab
from ipylab._compat.enum import StrEnum
from ipylab._compat.typing import NotRequired, TypedDict

__all__ = ["Area", "Obj", "InsertMode", "Transform", "TransformType", "hookimpl", "pack", "IpylabKwgs"]

hookimpl = pluggy.HookimplMarker("ipylab")  # Used for plugins

if TYPE_CHECKING:
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
    """Return serialized obj if it is a Widget or string of code."""

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


class Transform(StrEnum):
    """An eumeration of transformations than can be applied to serialized data.

    Data sent between the kernel and Frontend is serialized using JSON. The transform is used
    to specify how that data should be transformed either prior to sending and/or once received.

    Transformations that require parameters should be specified in a dict with the key 'transform' specifying
    the transform, and other keys providing the parameters accordingly.

    - raw: [default] No conversion. Note: data is serialized when sending, some object serialization will fail.
    - function: Use a function to calculate the return value. ['code'] = 'function...'
    - connection: Return a connection to a disposable object in the frontend.
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
        "info": {} # Optional Dict of info.
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
    done = "done"
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
                    if cid and not isinstance(cid, str):
                        raise TypeError
                    transform_ = TransformDictConnection(transform=Transform.connection, cid=cid)
                    if info := transform.get("info"):
                        transform_["info"] = dict(info)
                    return transform_
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
    async def transform_payload(cls, transform: TransformType, payload):
        """Transform the payload according to the transform."""
        transform_ = transform["transform"] if isinstance(transform, dict) else transform
        match transform_:
            case Transform.advanced:
                mappings = typing.cast(TransformDictAdvanced, transform)["mappings"]
                return {key: await cls.transform_payload(mappings[key], payload[key]) for key in mappings}
            case Transform.connection:
                # Use a context to ensure the connection is valid.
                async with ipylab.Connection(payload["cid"]) as conn:
                    return conn
            case Transform.auto:
                if isinstance(payload, dict) and (cid := payload.get("cid")):
                    async with ipylab.Connection(cid) as conn:
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
    code: NotRequired[str]


class TransformDictAdvanced(TypedDict):
    transform: Literal[Transform.advanced]
    mappings: dict[str, TransformType]


class TransformDictConnection(TypedDict):
    transform: Literal[Transform.connection]
    cid: NotRequired[str | None]
    auto_dispose: NotRequired[bool]
    info: NotRequired[dict]


TransformType = Transform | TransformDictAdvanced | TransformDictFunction | TransformDictConnection


class IpylabKwgs(TypedDict):
    transform: NotRequired[TransformType]
    toLuminoWidget: NotRequired[list[str]]  # noqa: N815
    toObject: NotRequired[list[str]]  # noqa: N815
    hooks: NotRequired[TaskHookType]


class TaskHooks(TypedDict):
    """Hooks to run after successful completion of 'aw' passed to the method "to_task"
    and prior to returning.

    This provides a convenient means to set traits of the returned result.

    see: `Hookspec.task_result`
    """

    close_with_rev: NotRequired[list[Ipylab]]
    close_with_fwd: NotRequired[list[Widget]]

    trait_add_rev_: NotRequired[list[tuple[str, HasTraits]]]
    trait_add_fwd: NotRequired[list[tuple[str, Any]]]

    tuple_add_rev: NotRequired[list[tuple[str, Any]]]
    tuple_add_fwd: NotRequired[list[tuple[str, Ipylab]]]


TaskHookType = TaskHooks | None
