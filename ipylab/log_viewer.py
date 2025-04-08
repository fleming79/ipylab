# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import collections
from typing import TYPE_CHECKING, Self

from IPython.display import Markdown
from ipywidgets import HTML, BoundedIntText, Button, Checkbox, Combobox, Dropdown, HBox, Select, VBox
from traitlets import directional_link, link, observe
from typing_extensions import override

import ipylab
from ipylab.common import SVGSTR_TEST_TUBE, Fixed, InsertMode, autorun
from ipylab.log import LogLevel
from ipylab.simple_output import AutoScroll, SimpleOutput
from ipylab.widgets import AddToShellType, Icon, Panel

if TYPE_CHECKING:
    import logging


__all__ = ["LogViewer"]


class LogViewer(Panel):
    "A log viewer and an object viewer combined."

    _updating = False
    info = Fixed(lambda _: HTML(layout={"flex": "1 0 auto", "margin": "0px 20px 0px 20px"}))
    add_to_shell_defaults = AddToShellType(mode=InsertMode.split_bottom)

    log_level = Fixed[Self, Dropdown](
        lambda _: Dropdown(
            description="Level",
            options=[(v.name.capitalize(), v) for v in LogLevel],
            layout={"width": "max-content"},
        ),
        created=lambda c: link(
            source=(c["owner"].app, "log_level"),
            target=(c["obj"], "value"),
        ),
    )
    buffer_size: Fixed[Self, BoundedIntText] = Fixed(
        lambda _: BoundedIntText(
            value=100,
            description="Buffer size",
            min=1,
            max=1e6,
            layout={"width": "max-content", "flex": "0 0 auto"},
        ),
        created=lambda c: (
            c["obj"].observe(c["owner"]._observe_buffer_size, "value"),  # noqa: SLF001
            link(
                source=(c["obj"], "value"),
                target=(c["owner"].output, "max_outputs"),
            ),
            directional_link(
                source=(c["owner"].output, "length"),
                target=(c["obj"], "tooltip"),
                transform=lambda size: f"Current size: {size}",
            ),
        ),
    )
    button_show_send_dialog = Fixed[Self, Button](
        lambda _: Button(
            description="📪",
            tooltip="Send the record to the console.\n"
            "The record has the properties 'owner' and 'obj'attached "
            "which may be of interest for debugging purposes.",
            layout={"width": "auto", "flex": "0 0 auto"},
        ),
        created=lambda c: c["obj"].on_click(c["owner"]._button_on_click),  # noqa: SLF001
    )
    button_clear = Fixed[Self, Button](
        lambda _: Button(
            description="⌧",
            tooltip="Clear log",
            layout={"width": "auto", "flex": "0 0 auto"},
        ),
        created=lambda c: c["obj"].on_click(c["owner"]._button_on_click),  # noqa: SLF001
    )
    autoscroll_enabled = Fixed(
        lambda _: Checkbox(
            description="Auto scroll",
            indent=False,
            tooltip="Automatically scroll to the most recent logs.",
            layout={"width": "auto", "flex": "0 0 auto"},
        ),
    )
    header: Fixed[Self, HBox] = Fixed(
        lambda c: HBox(
            children=(
                c["owner"].info,
                c["owner"].autoscroll_enabled,
                c["owner"].log_level,
                c["owner"].buffer_size,
                c["owner"].button_clear,
                c["owner"].button_show_send_dialog,
            ),
            layout={"justify_content": "space-between", "flex": "0 0 auto"},
        ),
    )
    output = Fixed(SimpleOutput)
    autoscroll_widget: Fixed[Self, AutoScroll] = Fixed(
        lambda c: AutoScroll(content=c["owner"].output),
        created=lambda c: link(
            source=(c["owner"].autoscroll_enabled, "value"),
            target=(c["obj"], "enabled"),
        ),
    )

    def __init__(self):
        self._records = collections.deque(maxlen=100)
        self.title.icon = Icon(name="ipylab-test_tube", svgstr=SVGSTR_TEST_TUBE)
        super().__init__(children=[self.header, self.autoscroll_widget])
        if self.app.logging_handler:
            self.app.logging_handler.register_callback(self._add_record)

    @override
    def close(self, *, force=False):
        if force:
            super().close()

    @observe("connections")
    def _observe_connections(self, _):
        if self.connections and len(self.connections) == 1:
            self.output.push(*(rec.output for rec in self._records), clear=True)  # type: ignore
        self.info.value = f"<b>Vpath: {self.app._vpath}</b>"  # noqa: SLF001
        self.title.label = f"Log: {self.app._vpath}"  # noqa: SLF001

    def _add_record(self, record: logging.LogRecord):
        self._records.append(record)
        if self.connections:
            self.output.push(record.output)  # type: ignore
        if record.levelno >= LogLevel.ERROR and self.app._ready:  # noqa: SLF001
            self._notify_exception(True, record)

    @autorun
    async def _notify_exception(self, record: logging.LogRecord):
        "Create a notification that an error occurred."
        await self.app.notification.notify(
            message=f"Error: {record.msg}",
            type=ipylab.NotificationType.error,
            actions=[
                ipylab.NotifyAction(
                    label="📄",
                    caption="Show log viewer.",
                    callback=lambda: self._show_error(record=record),
                    keep_open=True,
                )
            ],
        )

    def _observe_buffer_size(self, change):
        if change["owner"] is self.buffer_size:
            self._records = collections.deque(self._records, maxlen=self.buffer_size.value)

    def _button_on_click(self, b):
        if b is self.button_show_send_dialog:
            b.disabled = True
            self._show_send_dialog(True, b)
        elif b is self.button_clear:
            self._records.clear()
            self.output.push(clear=True)

    @autorun
    async def _show_error(self, record: logging.LogRecord):
        out = SimpleOutput().push(Markdown(f"**{record.levelname.capitalize()}**:\n\n{record.message}"))
        try:
            out.push(record.output)  # type: ignore
        except Exception:
            out.push(record.message)
        objects = {
            "record": record,
            "owner": (owner := getattr(record, "owner", None)) and owner(),
            "obj": getattr(record, "obj", None),
        }
        b = Button(description="Send to console", tooltip="Send record, owner and obj to the console.")
        b.on_click(lambda _: self.app.shell.start_coro(self.app.shell.open_console(objects=objects)))
        out.push(b)
        await self.app.shell.add(out, mode=InsertMode.split_right)

    @autorun
    async def _show_send_dialog(self, b: Button):
        options = {f"{r.asctime}: {r.msg}": r for r in reversed(self._records)}  # type: ignore
        search = Combobox(
            placeholder="Search",
            tooltip="Search for a log entry or object.",
            ensure_option=True,
            layout={"width": "auto"},
            options=tuple(options),
        )
        select = Select(
            value=None,
            tooltip="Most recent exception is first",
            layout={"flex": "2 1 auto", "width": "auto", "height": "max-content"},
            options=options,
        )
        record_out = SimpleOutput()
        body = VBox([search, select, record_out])

        def observe(change: dict):
            if change["owner"] is select:
                record = select.value
                items = (record.output,) if record else ()
                record_out.push(*items, clear=True)
            elif change["owner"] is search and change["new"] in options:
                select.value = options[change["new"]]

        select.observe(observe, "value")
        search.observe(observe, "value")
        try:
            result = await self.app.dialog.show_dialog("Send record to console", body=body)
            if record := result["value"] and select.value:
                objects = {
                    "record": record,
                    "owner": (owner := getattr(record, "owner", None)) and owner(),
                    "obj": getattr(record, "obj", None),
                }
                await self.app.shell.open_console(objects=objects)
        except Exception:
            return
        finally:
            b.disabled = False
            for w in [search, body, select]:
                w.close()
