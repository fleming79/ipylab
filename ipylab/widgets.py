# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import ClassVar, NotRequired, TypedDict, Unpack

import anyio
from ipywidgets import Box, DOMWidget, Layout, TypedTuple, Widget, register, widget_serialization
from ipywidgets.widgets.trait_types import InstanceDict
from traitlets import Container, Dict, Instance, Tuple, Unicode, observe

import ipylab
import ipylab._frontend as _fe
from ipylab.common import Area, Fixed, InsertMode, autorun
from ipylab.connection import ShellConnection
from ipylab.ipylab import WidgetBase


class AddToShellType(TypedDict):
    area: NotRequired[Area]
    activate: NotRequired[bool]
    mode: NotRequired[InsertMode]
    rank: NotRequired[int | None]
    ref: NotRequired[ShellConnection | None]
    options: NotRequired[dict | None]


@register
class Icon(WidgetBase, DOMWidget):
    _model_name = Unicode("IconModel").tag(sync=True)
    _view_name = Unicode("IconView").tag(sync=True)

    name = Unicode().tag(sync=True)
    svgstr = Unicode().tag(sync=True)


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
class Panel(Box):
    _model_name = Unicode("PanelModel").tag(sync=True)
    _view_name = Unicode("PanelView").tag(sync=True)
    _model_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _model_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)
    _view_module = Unicode(_fe.module_name, read_only=True).tag(sync=True)
    _view_module_version = Unicode(_fe.module_version, read_only=True).tag(sync=True)
    title: Instance[Title] = InstanceDict(Title, ()).tag(sync=True, **widget_serialization)

    app = Fixed(lambda _: ipylab.App())
    connections: Container[tuple[ShellConnection, ...]] = TypedTuple(trait=Instance(ShellConnection))
    add_to_shell_defaults: ClassVar = AddToShellType(mode=InsertMode.tab_after)

    async def add_to_shell(self, **kwgs: Unpack[AddToShellType]) -> ShellConnection:
        """Add this panel to the shell."""
        return await self.app.shell.add(self, **self.add_to_shell_defaults | kwgs)


@register
class SplitPanel(Panel):
    _model_name = Unicode("SplitPanelModel").tag(sync=True)
    _view_name = Unicode("SplitPanelView").tag(sync=True)
    orientation = Unicode("vertical").tag(sync=True)
    layout = InstanceDict(Layout, kw={"width": "100%", "height": "100%", "overflow": "hidden"}).tag(
        sync=True, **widget_serialization
    )
    _force_update_in_progress = False

    # ============== Start temp fix =============
    # Below here is added as a temporary fix to address issue https://github.com/jtpio/ipylab/issues/129

    @observe("children", "connections")
    def _observer(self, _):
        self._toggle_orientation(children=self.children)

    @autorun
    async def _toggle_orientation(self, children: tuple[Widget, ...]):
        """Toggle the orientation to cause lumino_widget.parent to re-render content."""
        if children != self.children:
            return
        await anyio.sleep(0.1)
        orientation = self.orientation
        self.orientation = "horizontal" if orientation == "vertical" else "vertical"
        await anyio.sleep(0.001)
        self.orientation = orientation

    # ============== End temp fix =============


@register
class ResizeBox(Box):
    """A box that can be resized.

    All views of the box are resizeable via the handle on the bottom right corner.
    When a view is resized the other views are also resized to the same width and height.
    The `size` trait of this object provides the size in pixels as (client width, client height).

    Reference
    ---------
    * [width](https://developer.mozilla.org/en-US/docs/Web/CSS/width)
    * [height](https://developer.mozilla.org/en-US/docs/Web/CSS/height)
    * [client width](https://developer.mozilla.org/en-US/docs/Web/API/Element/clientWidth)
    * [client height](https://developer.mozilla.org/en-US/docs/Web/API/Element/clientHeight)
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
