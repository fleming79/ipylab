# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from ipywidgets import DOMWidget, Widget, register
from traitlets import Bool, Callable, Enum, Int, Unicode, default

from ipylab.ipylab import Ipylab

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any, Unpack

    from IPython.display import TextDisplayObject

    from ipylab.common import IpylabKwgs
from typing import TYPE_CHECKING

from ipywidgets import widget_serialization
from traitlets import Instance, observe

from ipylab.ipylab import WidgetBase

if TYPE_CHECKING:
    from typing import Unpack


@register
class SimpleOutput(Ipylab, DOMWidget):
    """An output with no prompts designed to accept frequent additions.

    Note: Widget restoration is not supported.
    """

    _model_name = Unicode("SimpleOutputModel").tag(sync=True)
    _view_name = Unicode("SimpleOutputView").tag(sync=True)
    max_outputs = Int(100, help="The maximum number of individual widgets").tag(sync=True)
    max_continuous_streams = Int(100, help="Max streams to put in same output").tag(sync=True)
    length = Int(read_only=True, help="The current length of the output area").tag(sync=True)
    format = Callable(allow_none=True, default_value=None)

    @default("format")
    def _default_format(self) -> Any | None:
        try:
            return self.comm.kernel.shell.display_formatter.format  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
        except AttributeError:
            return None

    def _pack_outputs(
        self, outputs: tuple[dict[str, str] | Widget | str | TextDisplayObject | Any, ...], *, stream_text=False
    ) -> Generator[dict[Any, Any], Any, None]:
        fmt = self.format
        for output in outputs:
            if isinstance(output, dict) and "output_type" in output:
                yield output
            elif stream_text and isinstance(output, str):
                yield {"output_type": "stream", "name": "stdout", "text": output}
            elif fmt:
                data, metadata = fmt(output)
                yield {"output_type": "display_data", "data": data, "metadata": metadata}
            elif hasattr(output, "_repr_mimebundle_") and callable(output._repr_mimebundle_):  # pyright: ignore[reportAttributeAccessIssue]
                yield {"output_type": "display_data", "data": output._repr_mimebundle_()}  # pyright: ignore[reportAttributeAccessIssue]
            else:
                yield {"output_type": "display_data", "data": repr(output)}

    def push(
        self, *outputs: dict[str, str] | Widget | str | TextDisplayObject | Any, clear=False, stream_text=False
    ) -> Self:
        """Add one or more items to the output.

        Consecutive `streams` of the same type are placed in the same 'output' up to `max_continuous_streams`.
        Outputs passed as dicts with a key "output_type" are assumed to be correctly packed as `repr_mime` data.

        Parameters
        ----------
        outputs:
            Items to be displayed.
        clear : bool
            Clear existing outputs prior to adding the outputs.
        stream_text : bool
            If True, treat string outputs as stdout streams.
        """

        items = list(self._pack_outputs(outputs, stream_text=stream_text))
        if items or clear:
            self.send({"add": items, "clear": clear})
        return self

    async def set(
        self, *outputs: dict[str, str] | Widget | str | TextDisplayObject | Any, **kwgs: Unpack[IpylabKwgs]
    ) -> int:
        """Set the output explicitly by first clearing and then adding the outputs.

        Compared to `push`, this is performed asynchronously and will wait for
        the frontend to be ready. The task will complete after the output has been
        added in the frontend.

        Parameters
        ----------
        outputs:
            Items to be displayed.
        """
        return await self.operation("setOutputs", {"items": list(self._pack_outputs(outputs))}, **kwgs)


@register
class AutoScroll(WidgetBase, DOMWidget):
    """An automatic scrolling container.

    The content can be changed and the scrolling enabled and disabled on the fly.

    Fast scrolling depends on `onscrollend`. Presently supported by common browsers except for Safari.
    https://developer.mozilla.org/en-US/docs/Web/API/Document/scrollend_event
    """

    _model_name = Unicode("AutoscrollModel").tag(sync=True)
    _view_name = Unicode("AutoscrollView").tag(sync=True)

    content = Instance(Widget, (), allow_none=True).tag(sync=True, **widget_serialization)

    enabled = Bool().tag(sync=True)
    mode = Enum(["start", "end"], "end").tag(sync=True)
    sentinel_text = Unicode(".", help="Provided for debugging purposes").tag(sync=True)

    @observe("enabled")
    def _observe(self, _) -> None:
        layout = self.layout
        with layout.hold_trait_notifications():
            if self.enabled:
                layout.overflow = "hidden"
                layout.height = "100%"
            else:
                layout.overflow = "auto"
                layout.height = "auto"

    def __init__(self, *, enabled=True, **kwargs) -> None:
        self.enabled = enabled
        super().__init__(**kwargs)
