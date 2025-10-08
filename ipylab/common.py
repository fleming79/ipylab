# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import contextlib
import importlib
import inspect
import textwrap
import typing
import weakref
from collections import OrderedDict
from collections.abc import Callable
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Literal,
    NotRequired,
    ParamSpec,
    Self,
    TypedDict,
    TypeVar,
    TypeVarTuple,
    final,
)

import anyio
import traitlets
from ipywidgets import TypedTuple, Widget, widget_serialization
from traitlets import Any as AnyTrait
from traitlets import Bool, Container, HasTraits, Instance, default, observe
from typing_extensions import override

import ipylab

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable

    from ipylab.ipylab import Ipylab
    from ipylab.log import IpylabLoggerAdapter

__all__ = [
    "Area",
    "Fixed",
    "FixedCreate",
    "FixedCreated",
    "HasApp",
    "InsertMode",
    "IpylabKwgs",
    "LastUpdatedDict",
    "Obj",
    "Singular",
    "Transform",
    "TransformType",
    "pack",
]


T = TypeVar("T")
S = TypeVar("S")
R = TypeVar("R")
B = TypeVar("B", bound=object)
L = TypeVar("L", bound="Ipylab")
P = ParamSpec("P")
PosArgsT = TypeVarTuple("PosArgsT")



def pack(obj: Widget | inspect._SourceObjectType):
    """Pack obj in a format usable in the frontend.

    Only widgets and source are packed, all other objects are passed without
    modification.

    Normally it is unnecessary to pack widgets or code because it is done
    automatically. It may be useful to use pack in connection with `toObject`
    to specify the frontend to extract a parameter in the frontend.

    See `app.shell.add` for an example of where pack is used.
    """

    if isinstance(obj, Widget):
        return widget_serialization["to_json"](obj, None)
    if inspect.isfunction(obj) or inspect.ismodule(obj) or inspect.isclass(obj):
        with contextlib.suppress(BaseException):
            return module_obj_to_import_string(obj)
        return textwrap.dedent(inspect.getsource(obj))
    msg = f"Unable pack this type of object {type(obj)}: {obj!r}"
    raise TypeError(msg)


def to_selector(*args, prefix="ipylab"):
    "Create a canonical selector from args."
    suffix = ("".join((" ".join(map(str, args))).split())).replace(".", "-")
    suffix = "".join(s if s.isnumeric() or s.isalpha() or s in "_-" else "-" for s in suffix)
    while "--" in suffix:
        suffix = suffix.replace("--", "-")
    suffix = suffix.strip(" -")
    return f".{prefix}-{suffix}"


def import_item(dottedname: str):
    """Import an item from a module, given its dotted name.

    For example:
    >>> import_item("os.path.join")
    """
    modulename, objname = dottedname.rsplit(".", maxsplit=1)
    return getattr(importlib.import_module(modulename), objname)


def module_obj_to_import_string(obj):
    """Convert a module object to an import string compatible with `app.evaluate`.

    Parameters
    ----------
    obj : object
        The module object to convert.

    Returns
    -------
    str
        The import string for the module object.

    Raises
    ------
    TypeError
        If the module object cannot be imported correctly.
    """
    dottedname = f"{obj.__module__}.{obj.__qualname__}"
    if dottedname.startswith("__main__"):
        msg = f"{obj=} won't be importable from a new kernel"
        raise TypeError(msg)
    item = import_item(dottedname)
    if item is not obj:
        msg = "Failed to import item correctly"
        raise TypeError(msg)
    return f"import_item({dottedname=})"


class Obj(StrEnum):
    "The objects available to use as 'obj' in the frontend."

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


@final
class Transform(StrEnum):
    """An eumeration of transformations to apply to the result of an operation
    performed on the frontend prior to returning to Python and transformation
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
        "connection_id": "ID TO USE FOR CONNECTION",
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
                    connection_id = transform.get("connection_id")
                    if connection_id and not connection_id.startswith(ipylab.Connection._PREFIX):
                        msg = (
                            f"'connection_id' should start with '{ipylab.Connection._PREFIX}' but got {connection_id=}"
                        )
                        raise ValueError(msg)
                    return TransformDictConnection(transform=Transform.connection, connection_id=connection_id)
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
    async def transform_payload(cls, transform: TransformType, payload) -> Any:
        """Transform the payload according to the transform."""
        transform_ = transform["transform"] if isinstance(transform, dict) else transform
        match transform_:
            case Transform.advanced:
                mappings = typing.cast("TransformDictAdvanced", transform)["mappings"]
                return {key: await cls.transform_payload(mappings[key], payload[key]) for key in mappings}
            case Transform.connection | Transform.auto if isinstance(payload, dict) and (
                connection_id := payload.get("connection_id")
            ):
                try:
                    conn = ipylab.Connection.get_connection(connection_id)
                except KeyError:
                    if transform_ == Transform.connection:
                        raise
                else:
                    return await conn.ready()
        return payload


class TransformDictFunction(TypedDict):
    transform: Literal[Transform.function]
    code: str


class TransformDictAdvanced(TypedDict):
    transform: Literal[Transform.advanced]
    mappings: dict[str, TransformType]


class TransformDictConnection(TypedDict):
    transform: Literal[Transform.connection]
    connection_id: NotRequired[str | None]


TransformType = Transform | TransformDictAdvanced | TransformDictFunction | TransformDictConnection


class SignalCallbackData(TypedDict, Generic[L]):
    dottedname: str
    args: dict | str | float | int | None
    owner: L


class IpylabKwgs(TypedDict):
    transform: NotRequired[TransformType]
    toLuminoWidget: NotRequired[list[str] | None]
    toObject: NotRequired[list[str] | None]


class LastUpdatedDict(OrderedDict):
    """Store items in the order the keys were last added.

    mode: Literal["first", "last"]
        The end to shift the last added key."""

    # ref: https://docs.python.org/3/library/collections.html#ordereddict-examples-and-recipes
    _updating = False
    _last = True

    def __init__(self, *args, mode: Literal["first", "last"] = "last", **kwargs) -> None:
        self._last = mode == "last"
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if not self._updating:
            self.move_to_end(key, self._last)

    @override
    def update(self, m, /, **kwargs) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._updating = True
        try:
            super().update(m, **kwargs)
        finally:
            self._updating = False


class FixedCreate(TypedDict, Generic[S]):
    "A TypedDict relevant to Fixed"

    name: str
    owner: S


class FixedCreated(TypedDict, Generic[S, T]):
    "A TypedDict relevant to Fixed"

    name: str
    owner: S
    obj: T


class Fixed(Generic[S, T]):
    """Descriptor for creating and caching a fixed instance of a class.

    The ``Fixed`` descriptor provisions for each instance of the owner class
    to dynamically load or import the managed class.  The managed instance
    is created on first access and then cached for subsequent access.

    Type Hints:
        ``S``: Type of the owner class.
        ``T``: Type of the managed class.

    Examples:
        >>> class MyClass:
        ...     fixed_instance = Fixed(ManagedClass)
        >>> my_object = MyClass()
        >>> instance1 = my_object.fixed_instance
        >>> instance2 = my_object.fixed_instance
        >>> instance1 is instance2
        True
    """

    __slots__ = ["create", "created", "instances", "name"]

    def __init__(
        self,
        obj: type[T] | Callable[[FixedCreate[S]], T] | str,
        /,
        *,
        created: Callable[[FixedCreated[S, T]]] | None = None,
    ):
        if inspect.isclass(obj):
            self.create = lambda _: obj()
        elif callable(obj):
            self.create = obj
        elif isinstance(obj, str):
            self.create = lambda _: import_item(obj)()
        else:
            msg = f"{obj=} is invalid. Wrap it with a lambda to make it 'constant'. Eg. lambda _: {obj}"
            raise TypeError(msg)
        self.created = created
        self.instances = weakref.WeakKeyDictionary()

    def __set_name__(self, owner_cls: type[S], name: str):
        self.name = name

    def __get__(self, obj: S, objtype: type[S] | None = None) -> T:
        if obj is None:
            return self  # pyright: ignore[reportReturnType]
        try:
            return self.instances[obj]
        except KeyError:
            instance: T = self.create(FixedCreate(name=self.name, owner=obj))  # pyright: ignore[reportAssignmentType]
            self.instances[obj] = instance
            if self.created:
                try:
                    self.created(FixedCreated(owner=obj, obj=instance, name=self.name))
                except Exception:
                    if log := getattr(obj, "log", None):
                        msg = f"Callback `created` failed for {obj.__class__}.{self.name}"
                        log.exception(msg, extra={"obj": self.created})
            return instance

    def __set__(self, obj: S, value: Self):
        # Note: above we use `Self` for the `value` type hint to give a useful typing error
        msg = f"Setting `Fixed` parameter {obj.__class__.__name__}.{self.name} is forbidden!"
        raise AttributeError(msg)


class HasApp(HasTraits):
    """A mixin class that provides access to the ipylab application.

    It provides methods for:

    - Closing other widgets when the widget is closed.
    - Adding the widget to a tuple of widgets owned by another object.
    - Starting coroutines in the main event loop.
    - Logging exceptions that occur when awaiting an awaitable.
    """

    _tuple_owners: Fixed[Self, set[tuple[HasTraits, str]]] = Fixed(set)
    _close_extras: Fixed[Self, weakref.WeakSet[Widget | HasApp]] = Fixed(weakref.WeakSet)

    closed = Bool(read_only=True)
    log: Instance[IpylabLoggerAdapter] = Instance("ipylab.log.IpylabLoggerAdapter")
    app = Fixed(lambda _: ipylab.JupyterFrontEnd())
    add_traits = None  # pyright: ignore[reportAssignmentType] Don't support the method HasTraits.add_traits as it creates a new type that isn't a subclass of its origin)

    @default("log")
    def _default_log(self):
        return ipylab.log.IpylabLoggerAdapter(self.__module__, owner=self)

    @observe("closed")
    def _hasapp_observe_closed(self, _):
        if self.closed:
            self.log.debug("closed")
            for item in list(self._close_extras):
                item.close()
            for obj, name in list(self._tuple_owners):
                if val := getattr(obj, name, None):
                    if (isinstance(obj, HasApp) and obj.closed) or (isinstance(obj, Widget) and not obj.comm):
                        return
                    obj.set_trait(name, tuple(v for v in val if v is not self))

    def _check_closed(self):
        if self.closed:
            msg = f"This instance is closed {self!r}"
            raise RuntimeError(msg)

    def close_with_self(self, obj: Widget | HasApp):
        """Register an object to be closed when this object is closed.

        Args:
        obj : The object to close.

        Raises:
            anyio.ClosedResourceError: If this object is already closed.
        """
        if self.closed:
            obj.close()
            msg = f"{self} is closed"
            raise anyio.ClosedResourceError(msg)
        self._close_extras.add(obj)

    def add_to_tuple(self, owner: HasTraits, name: str):
        """Add self to the tuple of obj and remove self when closed."""

        items = getattr(owner, name)
        if not self.closed and self not in items:
            owner.set_trait(name, (*items, self))
        self._tuple_owners.add((owner, name))

    def close(self):
        if close := getattr(super(), "close", None):
            close()
        self.set_trait("closed", True)

    async def _catch_exceptions(self, aw: Awaitable) -> None:
        """Catches exceptions that occur when awaiting an awaitable.

        The exception is logged, but otherwise ignored.

        Args:
            aw: The awaitable to await.
        """
        try:
            await aw
        except BaseException as e:
            self.log.exception(f"Calling {aw}", obj={"aw": aw}, exc_info=e)  # noqa: G004


class _SingularInstances(HasTraits, Generic[T]):
    instances: Container[tuple[T, ...]] = TypedTuple(trait=traitlets.Any(), read_only=True)


class Singular(HasTraits):
    """A base class that ensures only one instance of a class exists for each unique
    key (except for None).

    This class uses a class-level dictionary `_singular_instances` to store instances,
    keyed by a value obtained from the `get_single_key` classmethod.  Subsequent calls to
    the constructor with the same key will return the existing instance. If key is
    None, a new instance is always created and a reference is not kept to the object.

    The class attribute `singular` maintains a tuple of the instances on a per-subclass basis
    (only instances with a `single_key` that is not None are included).
    """

    singular_init_started = traitlets.Bool(read_only=True)
    _singular_instances: ClassVar[dict[Hashable, Self]] = {}
    single_key = AnyTrait(default_value=None, allow_none=True, read_only=True)
    closed = Bool(read_only=True)
    singular: ClassVar[_SingularInstances[Self]]

    def __init_subclass__(cls) -> None:
        cls._singular_instances = {}
        cls.singular = _SingularInstances()

    @classmethod
    def get_single_key(cls, *args, **kwgs) -> Hashable:  # noqa: ARG003
        return cls

    def __new__(cls, /, *args, **kwgs) -> Self:
        key = cls.get_single_key(*args, **kwgs)
        if key is None or not (inst := cls._singular_instances.get(key)):
            new = super().__new__
            inst = new(cls) if new is object.__new__ else new(cls, *args, **kwgs)
            if key:
                cls._singular_instances[key] = inst
                inst.set_trait("single_key", key)
        return inst

    def __init__(self, /, *args, **kwgs):
        if self.singular_init_started:
            return
        self.set_trait("singular_init_started", True)
        super().__init__(*args, **kwgs)
        self.singular.set_trait("instances", tuple(self._singular_instances.values()))

    @observe("closed")
    def _singular_observe_closed(self, _):
        if self.closed and self.single_key is not None:
            self._singular_instances.pop(self.single_key, None)
            self.singular.set_trait("instances", tuple(self._singular_instances.values()))

    def close(self):
        if close := getattr(super(), "close", None):
            close()
        self.set_trait("closed", True)
