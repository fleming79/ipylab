# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

from typing import TYPE_CHECKING

from ipywidgets import register
from traitlets import Tuple, Unicode

from ipylab.common import Transform, pack
from ipylab.connection import InfoConnection
from ipylab.ipylab import Ipylab
from ipylab.widgets import Icon

if TYPE_CHECKING:
    from ipylab.commands import CommandConnection


class TooltipButtonConnection(InfoConnection):
    ""


@register
class CustomToolbar(Ipylab):
    _model_name = Unicode("CustomToolbarModel").tag(sync=True)
    toolbar_buttons = Tuple()
    "The buttons added to the notebook toolbar"

    async def add_button(
        self,
        name: str,
        command: CommandConnection,
        *,
        args=None,
        iconClass=None,
        icon: Icon | None = None,
        label=None,
        after=None,
        tooltip=None,
        className=None,
    ) -> TooltipButtonConnection:
        connection_id = TooltipButtonConnection.to_id(name)
        TooltipButtonConnection.close_if_exists(connection_id)

        tb: TooltipButtonConnection = await self.operation(
            "addToolbarButton",
            {
                "name": name,
                "commandId": str(command),
                "args": args or {},
                "icon": f"{pack(icon)}.labIcon" if isinstance(icon, Icon) else None,
                "iconClass": iconClass,
                "label": label,
                "tooltip": tooltip,
                "after": after,
                "className": className,
            },
            transform={"transform": Transform.connection, "connection_id": connection_id},
            toObject=["icon"] if isinstance(icon, Icon) else [],
        )
        tb.add_to_tuple(self, "toolbar_buttons")
        return tb