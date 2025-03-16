# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import importlib
import inspect
import typing
import weakref
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Literal,
    NotRequired,
    Self,
    TypedDict,
    TypeVar,
    override,
)

import pluggy
from ipywidgets import Widget, widget_serialization
from traitlets import Any as AnyTrait
from traitlets import Bool, HasTraits

import ipylab

__all__ = [
    "Area",
    "Obj",
    "InsertMode",
    "Transform",
    "TransformType",
    "hookimpl",
    "pack",
    "IpylabKwgs",
    "TaskHookType",
    "LastUpdatedDict",
    "Fixed",
    "FixedCreate",
    "FixedCreated",
    "Singular",
]

hookimpl = pluggy.HookimplMarker("ipylab")  # Used for plugins

SVGSTR_TEST_TUBE = '<svg version="1.1" id="Layer_1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 392.493 392.493" xml:space="preserve" fill="#000000"><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <polygon style="fill:#FFFFFF;" points="83.2,99.123 169.697,185.62 300.477,185.62 148.687,33.701 "></polygon> <g> <path style="fill:#56ACE0;" d="M21.851,348.917c0,12.024,9.826,21.786,21.786,21.786s21.786-9.826,21.786-21.786 c0-7.111-10.214-25.794-21.786-43.184C32,323.123,21.851,341.806,21.851,348.917z"></path> <path style="fill:#56ACE0;" d="M31.677,218.59c0,6.594,5.301,11.895,11.895,11.895s11.895-5.301,11.895-11.895 c-0.065-3.491-5.042-13.382-11.895-24.113C36.784,205.143,31.741,215.034,31.677,218.59z"></path> </g> <path style="fill:#194F82;" d="M372.622,226.864L164.073,18.315c3.943-4.267,3.879-10.925-0.323-15.063 c-3.62-3.556-10.02-5.042-15.451,0L52.687,98.864c-4.267,4.267-4.267,11.119,0,15.451c4.202,4.202,10.796,4.267,15.063,0.323 l208.549,208.55c25.471,27.345,73.503,25.729,96.259,0C399.127,296.618,399.127,253.499,372.622,226.864z M83.2,99.123 l65.422-65.358l151.919,151.919h-130.78L83.2,99.123z M357.172,307.737c-15.321,16.356-44.8,19.846-65.358,0L191.483,207.406 h130.844l34.844,34.844C375.208,260.351,375.208,289.701,357.172,307.737z"></path> <path style="fill:#FFC10D;" d="M357.172,307.737c18.036-18.036,18.036-47.386,0-65.422l-34.844-34.909H191.483l100.331,100.331 C312.436,327.584,341.851,324.093,357.172,307.737z"></path> <g> <path style="fill:#194F82;" d="M34.844,280.327C29.026,288.149,0,328.295,0,348.917c0,24.048,19.653,43.572,43.636,43.572 s43.572-19.523,43.572-43.572c0-20.622-29.026-60.768-34.844-68.59C48.291,274.767,39.046,274.767,34.844,280.327z M43.636,370.767 c-12.024,0-21.786-9.826-21.786-21.786c0-7.111,10.214-25.794,21.786-43.184c11.572,17.325,21.786,36.008,21.786,43.184 C65.422,360.941,55.661,370.767,43.636,370.767z"></path> <path style="fill:#194F82;" d="M43.636,252.335c18.618,0,33.745-15.127,33.745-33.681c0-15.063-19.071-41.956-24.954-49.842 c-4.073-5.56-13.382-5.56-17.519,0c-5.883,7.887-24.954,34.78-24.954,49.842C9.891,237.272,25.018,252.335,43.636,252.335z M43.636,194.541c6.853,10.731,11.895,20.622,11.895,24.113c0,6.594-5.301,11.895-11.895,11.895s-11.96-5.301-11.96-11.895 C31.741,215.163,36.784,205.272,43.636,194.541z"></path> </g> </g></svg>'

T = TypeVar("T")

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable
    from typing import overload

    from ipylab.ipylab import Ipylab

    @overload
    def pack(obj: Widget) -> str: ...
    @overload
    def pack(obj: inspect._SourceObjectType) -> str: ...  # Technically only modules and functions.
    @overload
    def pack(obj: T) -> T: ...


def pack(obj):
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
    if inspect.isfunction(obj) or inspect.ismodule(obj):
        return inspect.getsource(obj)
    return obj


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
                return ipylab.Connection.get_connection(cid)
        return payload


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
    toLuminoWidget: NotRequired[list[str] | None]
    toObject: NotRequired[list[str] | None]
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


def trait_tuple_add(owner: HasTraits, name: str, value: Any):
    "Add value to a tuple trait of owner if it already isn't in the tuple."
    items = getattr(owner, name)
    if value not in items:
        owner.set_trait(name, (*items, value))


class LastUpdatedDict(OrderedDict):
    """Store items in the order the keys were last added.

    mode: Literal["first", "last"]
        The end to shift the last added key."""

    # ref: https://docs.python.org/3/library/collections.html#ordereddict-examples-and-recipes
    _updating = False
    _last = True

    def __init__(self, *args, mode: Literal["first", "last"] = "last", **kwargs):
        self._last = mode == "last"
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if not self._updating:
            self.move_to_end(key, self._last)

    @override
    def update(self, m, **kwargs):
        self._updating = True
        try:
            super().update(m, **kwargs)
        finally:
            self._updating = False


class Singular(HasTraits):
    """A base class that ensures only one instance of a class exists for each unique key.

    This class uses a class-level dictionary `_single_instances` to store instances,
    keyed by a value obtained from the `get_single_key` method.  Subsequent calls to
    the constructor with the same key will return the existing instance. If key is
    None, a new instance is always created and a reference is not kept to the object.

    Attributes:
        _limited_init_complete (bool): A flag to prevent multiple initializations.
        _single_instances (dict[Hashable, Self]): A class-level dictionary storing the single instances.
        _single_key (AnyTrait): A read-only trait storing the key for the instance.
        closed (Bool): A read-only trait indicating whether the instance has been closed.

    Methods:
        get_single_key(*args, **kwgs) -> Hashable:
            A class method that returns the key used to identify the single instance.
            Defaults to returning the class itself.  Subclasses should override this
            method to provide a key based on the constructor arguments.

        __new__(cls, /, *args, **kwgs) -> Self:
            Overrides the default `__new__` method to implement the singleton behavior.
            It retrieves the key using `get_single_key`, and either returns an existing
            instance from `_single_instances` or creates a new instance and stores it.

        __init__(self, /, *args, **kwgs):
            Overrides the default `__init__` method to prevent multiple initializations
            of the same instance.  It only calls the superclass's `__init__` method once.

        __init_subclass__(cls) -> None:
            Overrides the default `__init_subclass__` method to reset the `_single_instances`
            dictionary for each subclass.

        close(self):
            Removes the instance from the `_single_instances` dictionary and calls the
            `close` method of the superclass, if it exists.  Sets the `closed` trait to True.
    """

    _limited_init_complete = False
    _single_instances: ClassVar[dict[Hashable, Self]] = {}
    _single_key = AnyTrait(read_only=True)
    closed = Bool(read_only=True)

    @classmethod
    def get_single_key(cls, *args, **kwgs) -> Hashable:  # noqa: ARG003
        return cls

    def __new__(cls, /, *args, **kwgs) -> Self:
        key = cls.get_single_key(*args, **kwgs)
        if key is None or not (inst := cls._single_instances.get(key)):
            new = super().__new__
            inst = new(cls) if new is object.__new__ else new(cls, *args, **kwgs)
            if key:
                cls._single_instances[key] = inst
                inst.set_trait("_single_key", key)
        return inst

    def __init__(self, /, *args, **kwgs):
        if self._limited_init_complete:
            return
        super().__init__(*args, **kwgs)
        self._limited_init_complete = True

    def __init_subclass__(cls) -> None:
        cls._single_instances = {}

    def close(self):
        self._single_instances.pop(self._single_key, None)
        if callable(close := getattr(super(), "close", None)):
            close()
        self.set_trait("closed", True)


class FixedCreate(Generic[T], TypedDict):
    "A TypedDict relevant to Fixed"

    name: str
    klass: type[T]
    owner: Any
    args: tuple
    kwgs: dict


class FixedCreated(Generic[T], TypedDict):
    "A TypedDict relevant to Fixed"

    name: str
    obj: T
    owner: Any


class Fixed(Generic[T]):
    __slots__ = ["name", "instances", "klass", "args", "kwgs", "dynamic", "create", "created"]

    def __init__(
        self,
        klass: type[T] | str,
        *args,
        dynamic: list[str] | None = None,
        create: Callable[[FixedCreate[T]], T] | str = "",
        created: Callable[[FixedCreated[T]]] | str = "",
        **kwgs,
    ):
        """Define an instance of `klass` as a cached read only property.
        `args` and `kwgs` are used to instantiate `klass`.

        Parameters:
        ----------

        dynamic: list[str]:
            A list of argument names to call during creation. It is called with obj (owner)
            as an argument.

        create: Callable[[FixedCreated], T] | str
            A function or method name to call to create the instance of klass.

        created: Callable[[FixedCreatedDict], None] | str
            A function or method name to call after the instance is created.

        **kwgs:
            `kwgs` to pass when instantiating `klass`. Arguments listed in dynamic
            are first called with obj as an argument to obtain the value to
            substitute in place of the dynamic function.
        """
        if callable(create) and len(inspect.signature(create).parameters) != 1:
            msg = "'create' must be a callable the accepts one argument."
            raise ValueError(msg)
        if callable(created) and len(inspect.signature(created).parameters) != 1:
            msg = "'created' must be a callable the accepts one argument."
            raise ValueError(msg)
        if dynamic:
            for k in dynamic:
                if not callable(kwgs[k]) or len(inspect.signature(kwgs[k]).parameters) != 1:
                    msg = f"Argument'{k}' must a callable that accepts one argument."
                    raise ValueError(msg)
        self.created = created
        self.create = create
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
            klass = import_item(self.klass) if isinstance(self.klass, str) else self.klass
            kwgs = self.kwgs
            if self.dynamic:
                kwgs = kwgs.copy()
                for k in self.dynamic:
                    kwgs[k] = kwgs[k](obj)
            if self.create:
                create = getattr(obj, self.create) if isinstance(self.create, str) else self.create
                kw = FixedCreate(name=self.name, klass=klass, owner=obj, args=self.args, kwgs=kwgs)
                instance = create(kw)  # type: ignore
                if not isinstance(instance, klass):
                    msg = f"Expected {self.klass} but {create=} returned {type(instance)}"
                    raise TypeError(msg)
            else:
                instance = klass(*self.args, **kwgs)
            self.instances[obj] = instance
            try:
                if self.created:
                    created = getattr(obj, self.created) if isinstance(self.created, str) else self.created
                    created(FixedCreated(owner=obj, obj=instance, name=self.name))
            except Exception:
                if log := getattr(obj, "log", None):
                    log.exception("Callback `created` failed", obj=self.created)
        return self.instances[obj]

    def __set__(self, obj, value):
        msg = f"Setting {obj.__class__.__name__}.{self.name} is forbidden!"
        raise AttributeError(msg)
