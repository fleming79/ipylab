# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import uuid
import weakref
from typing import TYPE_CHECKING, Any, ClassVar

from ipywidgets import Widget, register
from traitlets import Bool, Dict, Instance, Unicode, observe

from ipylab._compat.typing import override
from ipylab.ipylab import Ipylab

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Generator
    from typing import Literal, Self, overload


@register
class Connection(Ipylab):
    """This class provides a connection to an object in the frontend.

    `Connection` and subclasses of `Connection` are used extensiviely in ipylab
    to provide a connection to an object in the frontend (Javascript).

    Instances of `Connection` are created automatically when the transform is
    set as `Transform.connection` and also for `Transform.auto` when the payload
    looks like it is `disposable`.

    Each subclass of `Connection` is designated a `prefix` derived from the subclass
    name. Creating a new object will create an instance of the correct class
    according to the `cid`. Only one instance of an object will exist per `cid`
    in a kernel.

    Closing a connection will also disposed of the object in the frontend by
    default. This can be disabled by specify `dispose=False` or setting the
    trait (property) `auto_dispose=False`.

    See also `Transform.connection` for further detail about transforms.
    """

    _CLASS_DEFINITIONS: ClassVar[dict[str, type[Self]]] = {}
    _PREFIX = "ipylab-"
    _SEP = "|"
    prefix: ClassVar = f"{_PREFIX}Connection{_SEP}"

    _connections: weakref.WeakValueDictionary[str, Self] = weakref.WeakValueDictionary()
    _model_name = Unicode("ConnectionModel").tag(sync=True)
    cid = Unicode(read_only=True, help="connection id").tag(sync=True)
    _dispose = Bool(read_only=True).tag(sync=True)
    ipylab_base = None

    auto_dispose = Bool(False, read_only=True, help="Dispose of the object in frontend when closed.").tag(sync=True)

    def __init_subclass__(cls, **kwargs) -> None:
        cls.prefix = f"{cls._PREFIX}{cls.__name__}{cls._SEP}"
        cls._CLASS_DEFINITIONS[cls.prefix.strip(cls._SEP)] = cls
        super().__init_subclass__(**kwargs)

    def __new__(cls, cid: str, **kwgs):
        inst = cls._connections.get(cid)
        if not inst:
            cls = cls._CLASS_DEFINITIONS[cid.split(cls._SEP, maxsplit=1)[0]]
            cls._connections[cid] = inst = super().__new__(cls, **kwgs)
        return inst

    def __init__(self, cid: str, **kwgs):
        super().__init__(cid=cid, **kwgs)

    def __str__(self):
        return self.cid

    @property
    @override
    def repr_info(self):
        return {"cid": self.cid}

    @classmethod
    def to_cid(cls, *args: str) -> str:
        """Generate a cid."""
        args = tuple(aa for a in args if (aa := a.strip()))
        if args and args[0].startswith(cls.prefix):
            if len(args) != 1:
                msg = "Extending a cid with extra args is not allowed!"
                raise ValueError(msg)
            return args[0]
        if not args:
            args = (str(uuid.uuid4()),)
        return cls.prefix + cls._SEP.join(args)

    @classmethod
    def get_instances(cls) -> Generator[Self, Any, None]:
        "Get all instances of this class (including subclasses)."
        for item in cls._connections.values():
            if isinstance(item, cls):
                yield item

    @observe("comm")
    def _connection_observe_comm(self, _):
        if not self.comm:
            self._connections.pop(self.cid, None)

    def close(self, *, dispose=True):
        """Permanently close the widget.

        dispose: bool
            Whether to dispose of the object at the frontend."""
        self.set_trait("auto_dispose", dispose)
        super().close()

    if TYPE_CHECKING:

        @overload
        @classmethod
        def get_existing_connection(cls, cid: str, *, quiet: Literal[False]) -> Self: ...
        @overload
        @classmethod
        def get_existing_connection(cls, cid: str, *, quiet: Literal[True]) -> Self | None: ...
        @overload
        @classmethod
        def get_existing_connection(cls, cid: str) -> Self: ...

    @classmethod
    def get_existing_connection(cls, cid: str, *, quiet=False):
        """Get an existing connection.

        quiet: bool
            True: Raise a value error if the connection does not exist.
            False: Return None.
        """
        conn = cls._connections.get(cid)
        if not conn and not quiet:
            msg = f"A connection does not exist with '{cid=}'"
            raise ValueError(msg)
        return conn


Connection._CLASS_DEFINITIONS[Connection.prefix.strip(Connection._SEP)] = Connection  # noqa: SLF001


class InfoConnection(Connection):
    "A connection with info and auto_dispose enabled."

    info = Dict(help="info about the item")
    auto_dispose = Bool(True).tag(sync=True)

    @property
    @override
    def repr_info(self):
        return {"cid": self.cid, "info": self.info}


class ShellConnection(Connection):
    "A connection to a widget loaded in the shell."

    _model_name = Unicode("ShellConnectionModel").tag(sync=True)
    auto_dispose = Bool(True).tag(sync=True)

    widget = Instance(Widget, allow_none=True, default_value=None, help="The widget that has the view")

    def __del__(self):
        """Object disposal"""
        # Losing strong references doesn't mean the widget should be closed.
        self.close(dispose=False)

    def activate(self):
        "Activate the connected widget in the shell."

        return self.operation("activate")

    def get_session(self) -> Task[dict]:
        """Get the session of the connected widget."""
        return self.operation("getSession")
