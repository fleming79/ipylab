# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import ClassVar, NotRequired, TypedDict, Unpack

from ipywidgets import Box, DOMWidget, TypedTuple, register, widget_serialization
from ipywidgets.widgets.trait_types import InstanceDict
from traitlets import Container, Dict, Instance, Unicode

from ipylab.common import Area, HasApp, InsertMode
from ipylab.connection import Connection, ShellConnection
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
class Panel(HasApp, WidgetBase, Box):
    _model_name = Unicode("PanelModel").tag(sync=True)
    _view_name = Unicode("PanelView").tag(sync=True)
    title: Instance[Title] = InstanceDict(Title, ()).tag(sync=True, **widget_serialization)

    connections: Container[tuple[Connection, ...]] = TypedTuple(trait=Instance(Connection))
    add_to_shell_defaults: ClassVar = AddToShellType(mode=InsertMode.tab_after)

    async def add_to_shell(self, *, connection_id="", **kwgs: Unpack[AddToShellType]) -> ShellConnection:
        """Add this panel to the shell."""
        if connection_id:
            kwgs["connection_id"] = connection_id  # pyright: ignore[reportGeneralTypeIssues]
        return await self.app.shell.add(self, **self.add_to_shell_defaults | kwgs)


@register
class SplitPanel(Panel):
    _model_name = Unicode("SplitPanelModel").tag(sync=True)
    _view_name = Unicode("SplitPanelView").tag(sync=True)
    orientation = Unicode("vertical").tag(sync=True)

