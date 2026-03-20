# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, NotRequired, Self, TypedDict, Unpack
from uuid import uuid4

import anyio
from async_kernel import Caller
from async_kernel.common import Fixed
from ipywidgets import Box, DOMWidget, Layout, TypedTuple, Widget, register, widget_serialization
from ipywidgets.widgets.trait_types import InstanceDict
from traitlets import Bool, Container, Dict, Instance, Tuple, Unicode, observe
from typing_extensions import override

import ipylab._frontend as _fe
from ipylab.common import Area, HasApp, InsertMode
from ipylab.connection import Connection, ShellConnection
from ipylab.ipylab import WidgetBase

if TYPE_CHECKING:
    from collections.abc import Callable


__all__ = [
    "AddToShellType",
    "Icon",
    "KeyboardCapture",
    "KeyboardEventType",
    "Panel",
    "ResizeBox",
    "SplitPanel",
    "Title",
]


class AddToShellType(TypedDict):
    area: NotRequired[Area]
    activate: NotRequired[bool]
    mode: NotRequired[InsertMode]
    rank: NotRequired[int | None]
    ref: NotRequired[ShellConnection | None]
    options: NotRequired[dict | None]


class KeyboardEventType(TypedDict):
    "Keyboard events handled by KeyboardCapture."

    event: Literal["keyup", "keydown"]
    keyCode: str
    repeat: bool
    shiftKey: bool
    ctrlKey: bool
    altKey: bool


@register
class Icon(WidgetBase, DOMWidget):
    _model_name = Unicode("IconModel").tag(sync=True)
    _view_name = Unicode("IconView").tag(sync=True)

    name = Unicode(read_only=True).tag(sync=True)
    svgstr = Unicode().tag(sync=True)

    def __init__(self, name: str = "", **kwargs):
        self.set_trait("name", name or f"ipylab-icon-{uuid4()!s}")
        super().__init__(**kwargs)


@register
class Title(WidgetBase):
    _model_name = Unicode("TitleModel").tag(sync=True)

    label = Unicode().tag(sync=True)
    icon_class = Unicode().tag(sync=True)
    caption = Unicode().tag(sync=True)
    class_name = Unicode().tag(sync=True)
    dataset = Dict().tag(sync=True)
    icon_label = Unicode().tag(sync=True)
    # Widgets
    icon: Instance[Icon] = InstanceDict(Icon, allow_none=True).tag(sync=True, **widget_serialization)


@register
class Panel(HasApp, WidgetBase, Box):
    _model_name = Unicode("PanelModel").tag(sync=True)
    _view_name = Unicode("PanelView").tag(sync=True)
    title: Instance[Title] = InstanceDict(Title, ()).tag(sync=True, **widget_serialization)

    connections: Container[tuple[Connection, ...]] = TypedTuple(trait=Instance(Connection))
    add_to_shell_defaults: ClassVar = AddToShellType(mode=InsertMode.tab_after)

    async def add_to_shell(self, *, connection_id="", **kwgs: Unpack[AddToShellType]) -> ShellConnection[Self]:
        """Add this panel to the shell."""
        if connection_id:
            kwgs["connection_id"] = connection_id  # pyright: ignore[reportGeneralTypeIssues]
        return await self.app.shell.add(self, **self.add_to_shell_defaults | kwgs)


@register
class SplitPanel(Panel):
    _model_name = Unicode("SplitPanelModel").tag(sync=True)
    _view_name = Unicode("SplitPanelView").tag(sync=True)
    orientation = Unicode("vertical").tag(sync=True)
    layout = InstanceDict(Layout, kw={"width": "100%", "height": "100%", "overflow": "hidden"}).tag(
        sync=True, **widget_serialization
    )

    # ============== Start temp fix =============
    # Below here is added as a temporary fix to address issue https://github.com/jtpio/ipylab/issues/129

    @observe("children", "connections")
    def _observer(self, _):
        Caller("MainThread").queue_call(self._toggle_orientation, self.children)

    async def _toggle_orientation(self, children: tuple[Widget, ...]) -> None:
        """Toggle the orientation to cause lumino_widget.parent to re-render content."""
        await anyio.sleep(0.1)
        if children != self.children:
            return
        orientation = self.orientation
        self.orientation = "horizontal" if orientation == "vertical" else "vertical"
        await anyio.sleep(0.001)
        self.orientation = orientation

    # ============== End temp fix =============


@register
class ResizeBox(Box):
    """
    A box that can be resized.

    All views of the box are resizeable via the handle on the bottom right corner.
    When a view is resized the other views are also resized to the same width and height.
    The `size` trait of this object provides the size in pixels as (client width, client height).

    The following class names can be added to the widget to add a handle to make the widget user resizeable.

    - ipylab-ResizeBoth
    - ipylab-ResizeVertical
    - ipylab-ResizeHorizontal

    Reference:
        - [width](https://developer.mozilla.org/en-US/docs/Web/CSS/width)
        - [height](https://developer.mozilla.org/en-US/docs/Web/CSS/height)
        - [client width](https://developer.mozilla.org/en-US/docs/Web/API/Element/clientWidth)
        - [client height](https://developer.mozilla.org/en-US/docs/Web/API/Element/clientHeight)
    """

    _model_name = Unicode("ResizeBoxModel").tag(sync=True)
    _view_name = Unicode("ResizeBoxView").tag(sync=True)
    _model_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _model_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)
    _view_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _view_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)

    size: Container[tuple[int, int]] = Tuple(read_only=True, help="(clientWidth, clientHeight) in pixels").tag(
        sync=True
    )

    def _to_dim(self, val: str | int):
        try:
            return f"{int(val)}px"
        except Exception:
            return val

    def set_size(self, size: tuple[str | int, str | int]) -> None:
        "Set the size of the box."
        self.layout = {"width": self._to_dim(size[0]), "height": self._to_dim(size[1])}


@register
class KeyboardCapture(HasApp, DOMWidget):
    """
    A widget that captures all keystrokes while it is has the focus.

    Use 'register' method to add a handler.

    'keyDown' and 'keyUp' messages are captured.
    """

    _model_name = Unicode("KeyboardCaptureModel").tag(sync=True)
    _view_name = Unicode("KeyboardCaptureView").tag(sync=True)
    _model_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _model_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)
    _view_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _view_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)

    _handlers: Fixed[Any, set[Callable[[KeyboardEventType], Any]]] = Fixed(set)

    description = Unicode(help="Button label.").tag(sync=True)
    disabled = Bool(False, help="Enable or disable user changes.").tag(sync=True)
    icon = Unicode("", help="Font-awesome icon names, without the 'fa-' prefix.").tag(sync=True)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.on_msg(self._keyboardcapture_on_msg)

    def _keyboardcapture_on_msg(self, _, content: KeyboardEventType, buffers: list) -> None:
        if content.get("event"):
            for handler in self._handlers:
                self.app.caller.queue_call(handler, content)

    def register(self, func: Callable[[KeyboardEventType], Any]) -> None:
        """
        Register a handler.

        The handler can be a standard callable or coroutine function. As the messages are received the handler call is
        queued using Caller.queue_call.
        """
        self._handlers.add(func)

    def deregister(self, func: Callable[[KeyboardEventType], Any]) -> None:
        "Deregister a handler"
        self._handlers.discard(func)

    @override
    def close(self) -> None:
        super().close()
        self._handlers.clear()
