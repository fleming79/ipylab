# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import uuid
import weakref
from typing import TYPE_CHECKING, Any, ClassVar, override

from ipywidgets import Widget, register
from traitlets import Bool, Instance, Unicode, observe

from ipylab.ipylab import Ipylab

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Literal, overload

    from ipylab._compat.typing import Self


@register
class Connection(Ipylab):
    """A connection to a single object in the Frontend.

    `Connection` and subclasses of `Connection` are used extensiviely in Ipylab
    to provide a connection to an object in the frontend (Javascript).
    Instances of `Connection` are created automatically when the transform is
    set as `Transform.connection`. This option is available whenever a transform
    argument is available in a method call that goes to `operation`.

    When the `cid` *prefix* matches a subclass `CID_PREFIX`, a new subclass
    instance will be created in place of `Connection` (on the python side).

    When closing the connection the object in the frontend can be directed to
    to dispose. Some subclasses such as `CommandConnection`,`CommandPalletItemConnection`
    and `LauncherConnection` (a subclass of `CommandPalletItemConnection`) have dispose
    enabled by default.

    It is possible to create a connection to most objects in the frontend,
    non-disposable objects are patched with a blank `dispose` method.

    The `cid` will not change for the life of the object, the id may change
    when the Page is reloaded which causes the Javascript to restart. The
    intent of the object won't change. However, it is likely the connection
    won't be re-established meaning the connection will close.

    see: https://lumino.readthedocs.io/en/latest/api/modules/disposable.html

    If a specific subclass of Connection is required, the transform should be
    specified with the cid from the subclass. Use the keyword argument `cid` to
    ensure the subclass instance is returned. The class methods `to_cid` will
    generate an appropriate id.

    Once an object is registered in the frontend against a cid, it cannot be replaced
    until it has been removed. Keep in mind that cid's are specified in the frontend
    and can be shared between kernels. Currently each kerenel will have its own model
    per 'cid' and the 'id' may not stay in sync should it be 'changed', therefore it
    is recommended to not change the 'id' manually.

    See also `Transform.connection` for further detail about transforms.
    """

    _CLASS_DEFINITIONS: ClassVar[dict[str, type[Self]]] = {}
    _PREFIX = "ipylab-"
    _SEP = "|"
    _connections: weakref.WeakValueDictionary[str, Self] = weakref.WeakValueDictionary()
    _model_name = Unicode("ConnectionModel").tag(sync=True)
    cid = Unicode(read_only=True, help="connection id").tag(sync=True)
    prefix: ClassVar = f"{_PREFIX}Connection{_SEP}"
    auto_dispose = Bool(False, read_only=True, help="Dispose of the object in frontend when closed.").tag(sync=True)
    _dispose = Bool(read_only=True).tag(sync=True)
    ipylab_base = None

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
    def rep_info(self):
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
                yield item  # type: ignore

    @observe("comm")
    def _observe_comm(self, change: dict):
        if not self.comm:
            self._connections.pop(self.cid, None)
        super()._observe_comm(change)

    def close(self, *, dispose: None | bool = None):
        """Permanently close the widget.

        dispose: bool
            Whether to dispose of the object at the frontend."""
        if dispose:
            self.set_trait("auto_dispose", True)
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


Connection._CLASS_DEFINITIONS[Connection.prefix] = Connection  # noqa: SLF001


class ShellConnection(Connection):
    "Provides a connection to a widget loaded in the shell"

    _model_name = Unicode("ShellConnectionModel").tag(sync=True)

    widget = Instance(Widget, allow_none=True, default_value=None, help="The widget that has the view")
    auto_dispose = Bool(True).tag(sync=True)

    def activate(self):
        "Activate the connected widget in the shell."

        async def activate():
            await self.operation("activate")
            return self

        return self.to_task(activate())
