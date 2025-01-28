# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import collections
from typing import TYPE_CHECKING

from ipywidgets import HTML, BoundedIntText, Button, Checkbox, Combobox, Dropdown, HBox, Select, VBox
from traitlets import directional_link, link, observe

import ipylab
from ipylab.common import SVGSTR_TEST_TUBE, Area, InsertMode, Readonly
from ipylab.log import LogLevel
from ipylab.simple_output import AutoScroll, SimpleOutput
from ipylab.widgets import Icon, Panel

if TYPE_CHECKING:
    import logging
    from asyncio import Task

    from ipylab.connection import ShellConnection

__all__ = ["LogViewer"]


class LogViewer(Panel):
    "A log viewer and an object viewer combined."

    _log_notify_task: None | Task = None
    _updating = False
    info = Readonly(HTML, layout={"flex": "1 0 auto", "margin": "0px 20px 0px 20px"})
    log_level = Readonly(
        Dropdown,
        description="Level",
        options=[(v.name.capitalize(), v) for v in LogLevel],
        layout={"width": "max-content"},
    )
    buffer_size = Readonly(
        BoundedIntText,
        description="Buffer size",
        min=1,
        max=1e6,
        layout={"width": "max-content", "flex": "0 0 auto"},
        created=lambda c: c["obj"].observe(c["owner"]._observe_buffer_size, "value"),  # noqa: SLF001
    )
    button_show_send_dialog = Readonly(
        Button,
        description="📪",
        tooltip="Send the record to the console.\n"
        "The record has the properties 'owner' and 'obj'attached "
        "which may be of interest for debugging purposes.",
        layout={"width": "auto", "flex": "0 0 auto"},
    )
    button_clear = Readonly(
        Button,
        description="⌧",
        tooltip="Clear log",
        layout={"width": "auto", "flex": "0 0 auto"},
    )
    autoscroll_enabled = Readonly(
        Checkbox,
        description="Auto scroll",
        indent=False,
        tooltip="Automatically scroll to the most recent logs.",
        layout={"width": "auto", "flex": "0 0 auto"},
    )
    _default_header_children = (
        "info",
        "autoscroll_enabled",
        "log_level",
        "buffer_size",
        "button_clear",
        "button_show_send_dialog",
    )
    header = Readonly(
        HBox,
        children=lambda owner: [w for v in owner._default_header_children if (w := getattr(owner, v, None))],  # noqa: SLF001
        layout={"justify_content": "space-between", "flex": "0 0 auto"},
        dynamic=["children"],
    )
    output = Readonly(SimpleOutput)
    autoscroll_widget = Readonly(AutoScroll, content=lambda v: v.output, dynamic=["content"])

    def __init__(self, buffersize=100):
        self._records = collections.deque(maxlen=buffersize)
        self.title.icon = Icon(name="ipylab-test_tube", svgstr=SVGSTR_TEST_TUBE)
        super().__init__(children=[self.header, self.autoscroll_widget])
        self.buffer_size.value = buffersize
        app = ipylab.app
        link((self.autoscroll_widget, "enabled"), (self.autoscroll_enabled, "value"))
        link((app, "log_level"), (self.log_level, "value"))
        link((self.buffer_size, "value"), (self.output, "max_outputs"))
        directional_link(
            (self.output, "length"), (self.buffer_size, "tooltip"), transform=lambda size: f"Current size: {size}"
        )
        if app.logging_handler:
            app.logging_handler.register_callback(self._add_record)
        self.button_show_send_dialog.on_click(self._button_on_click)
        self.button_clear.on_click(self._button_on_click)

    def close(self):
        "Cannot close"

    @observe("connections")
    def _observe_connections(self, _):
        if self.connections and len(self.connections) == 1:
            self.output.push(*(rec.output for rec in self._records), clear=True)
        self.info.value = f"<b>Vpath: {ipylab.app.vpath}</b>"
        self.title.label = f"Log: {ipylab.app.vpath}"

    def _add_record(self, record: logging.LogRecord):
        self._records.append(record)
        if self.connections:
            self.output.push(record.output)  # type: ignore
        if record.levelno >= LogLevel.ERROR and ipylab.app._ready:  # noqa: SLF001
            self._notify_exception(record)

    def _notify_exception(self, record: logging.LogRecord):
        "Create a notification that an error occurred."
        if self._log_notify_task:
            # Limit to one notification.
            if not self._log_notify_task.done():
                return
            self._log_notify_task.result().close()
        self._log_notify_task = ipylab.app.notification.notify(
            message=f"Error: {record.msg}",
            type=ipylab.NotificationType.error,
            actions=[
                ipylab.NotifyAction(label="📄", caption="Show log viewer.", callback=self.add_to_shell, keep_open=True)
            ],
        )

    def _observe_buffer_size(self, change):
        if change["owner"] is self.buffer_size:
            self._records = collections.deque(self._records, maxlen=self.buffer_size.value)

    def _button_on_click(self, b):
        if b is self.button_show_send_dialog:
            self.button_show_send_dialog.disabled = True
            ipylab.app.dialog.to_task(
                self._show_send_dialog(),
                hooks={"callbacks": [lambda _: self.button_show_send_dialog.set_trait("disabled", False)]},
            )
        elif b is self.button_clear:
            self._records.clear()
            self.output.push(clear=True)

    async def _show_send_dialog(self):
        # TODO: make a formatter to simplify the message with obj and owner)
        options = {r.msg: r for r in reversed(self._records)}  # type: ignore
        select = Select(
            tooltip="Most recent exception is first",
            layout={"flex": "2 1 auto", "width": "auto", "height": "max-content"},
            options=options,
        )
        search = Combobox(
            placeholder="Search",
            tooltip="Search for a log entry or object.",
            ensure_option=True,
            layout={"width": "auto"},
            options=tuple(options),
        )
        body = VBox([select, search])

        def observe(change: dict):
            if change["owner"] is select:
                body.children = [select, search, select.value] if select.value else [select, search]
            elif change["owner"] is search and change["new"] in options:
                select.value = options[change["new"]]

        select.observe(observe, "value")
        search.observe(observe, "value")
        try:
            result = await ipylab.app.dialog.show_dialog("Send record to console", body=body)
            if result["value"] and select.value:
                console = await ipylab.app.shell.open_console(objects={"record": select.value})
                await console.set_property("console.promptCell.model.sharedModel.source", "record")
                await console.execute_method("console.execute")
        except Exception:
            return
        finally:
            for w in [search, body, select]:
                w.close()

    def add_to_shell(
        self,
        *,
        area: ipylab.Area = Area.main,
        activate: bool = True,
        mode: ipylab.InsertMode = InsertMode.split_bottom,
        rank: int | None = None,
        ref: ipylab.ShellConnection | None = None,
        options: dict | None = None,
        **kwgs,
    ) -> Task[ShellConnection]:
        return super().add_to_shell(
            area=area, activate=activate, mode=mode, rank=rank, ref=ref, options=options, **kwgs
        )
