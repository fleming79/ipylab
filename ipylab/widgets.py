# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ipywidgets import Box, DOMWidget, TypedTuple, register, widget_serialization
from ipywidgets.widgets.trait_types import InstanceDict
from traitlets import Container, Dict, Instance, Unicode, observe

import ipylab._frontend as _fe
from ipylab.common import Area, InsertMode
from ipylab.connection import ShellConnection
from ipylab.ipylab import WidgetBase

if TYPE_CHECKING:
    from asyncio import Task

    from ipylab import App


@register
class Icon(DOMWidget, WidgetBase):
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
    app: Instance[App] = Instance("ipylab.App", (), read_only=True)
    connections: Container[tuple[ShellConnection, ...]] = TypedTuple(trait=Instance(ShellConnection))

    def __init__(self, children=(), **kwargs):
        super().__init__(children, **kwargs)
        self.add_class("ipylab-" + self.__class__.__name__)

    def add_to_shell(
        self,
        *,
        area: Area = Area.main,
        activate: bool = True,
        mode: InsertMode = InsertMode.tab_after,
        rank: int | None = None,
        ref: ShellConnection | None = None,
        options: dict | None = None,
        **kwgs,
    ) -> Task[ShellConnection]:
        """Add this panel to the shell."""
        return self.app.shell.add(
            self,
            area=area,
            mode=mode,
            activate=activate,
            rank=rank,
            ref=ref,
            options=options,
            **kwgs,
        )


@register
class SplitPanel(Panel):
    _model_name = Unicode("SplitPanelModel").tag(sync=True)
    _view_name = Unicode("SplitPanelView").tag(sync=True)
    orientation = Unicode("vertical").tag(sync=True)
    _force_update_in_progress = False

    # ============== Start temp fix =============
    # Below here is added as a temporary fix to address issue https://github.com/jtpio/ipylab/issues/129
    def __init__(self, children=(), **kwargs):
        super().__init__(children, **kwargs)
        self.app.restored.register_callback(self._rerender)

    def close(self):
        super().close()
        self.app.restored.register_callback(self._rerender, True)

    @observe("children", "shell_connection")
    def _observe_children(self, _):
        self._rerender()

    def _rerender(self):
        """Toggle the orientation to cause lumino_widget.parent to re-render content."""

        async def force_refresh(children):
            if children != self.children:
                return
            await asyncio.sleep(0.1)
            orientation = self.orientation
            self.orientation = "horizontal" if orientation == "vertical" else "vertical"
            await asyncio.sleep(0.001)
            self.orientation = orientation

        return self.app.to_task(force_refresh(self.children))

    # ============== End temp fix =============
