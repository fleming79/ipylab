# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import collections
from typing import TYPE_CHECKING

from ipywidgets import HTML, BoundedIntText, Button, Checkbox, Combobox, Dropdown, HBox, Output, Select, VBox
from traitlets import directional_link, link

import ipylab
from ipylab.common import SVGSTR_TEST_TUBE, Area, InsertMode
from ipylab.log import IpylabLogHandler, LogLevel
from ipylab.simple_output import AutoScroll, SimpleOutput
from ipylab.widgets import Icon, Panel

if TYPE_CHECKING:
    from asyncio import Task

    from ipylab.connection import ShellConnection
    from ipylab.jupyterfrontend import App


class LogViewer(Panel):
    "A log viewer and an object viewer combined."

    _log_notify_task: None | Task = None
    _updating = False

    def __init__(self, app: App, handler: IpylabLogHandler, buffersize=100):
        self.info = HTML(
            f"<b>Vpath: {app.vpath}</b>",
            tooltip="Use this panel to access the log console from either:\n"
            "1. The icon in the status bar, or,\n"
            "2. The context menu (right click).\n"
            "The controls below are provided to put an object into a console.\n"
            "Note: Jupyterlab loads a different 'log console'  for the 'console'.",
            layout={"flex": "1 0 auto", "margin": "0px 20px 0px 20px"},
        )
        options = [(v.name.capitalize(), v) for v in LogLevel]
        self.log_level = Dropdown(
            description="Level",
            value=app.log_level,
            options=options,
            layout={"width": "max-content"},
        )
        self.buffer_size = BoundedIntText(
            description="Buffer size",
            value=buffersize,
            min=1,
            max=1e6,
            layout={"width": "max-content"},
        )
        self.button_show_send_dialog = Button(
            description="📪",
            tooltip="Send the record to the console.\n"
            "The record has the properties 'owner' and 'obj'attached "
            "which may be of interest for debugging purposes.",
            layout={"width": "auto"},
        )
        self.button_clear = Button(
            description="✗",
            tooltip="Clear output",
            layout={"width": "auto"},
        )
        self.autoscroll_enabled = Checkbox(
            description="Scroll",
            indent=False,
            tooltip="Scroll to the most recent logs.",
            layout={"width": "auto"},
        )
        self.box_controls = HBox(
            children=[
                self.info,
                self.autoscroll_enabled,
                self.log_level,
                self.buffer_size,
                self.button_clear,
                self.button_show_send_dialog,
            ],
            layout={"justify_content": "space-between", "flex": "0 0 auto"},
        )
        self.output = SimpleOutput()
        self.autoscroll_widget = AutoScroll(content=self.output)

        self.title.label = f"Log: {app.vpath}"
        self.title.icon = Icon(name="ipylab-test_tube", svgstr=SVGSTR_TEST_TUBE)
        self._records = collections.deque(maxlen=buffersize)

        super().__init__(children=[self.box_controls, self.autoscroll_widget])

        self.buffer_size.observe(self._observe_buffer_size, "value")
        handler.register_callback(self._add_record)
        link((self.autoscroll_widget, "enabled"), (self.autoscroll_enabled, "value"))
        link((app, "log_level"), (self.log_level, "value"))
        link((self.buffer_size, "value"), (self.output, "max_outputs"))
        directional_link(
            (self.output, "length"), (self.buffer_size, "tooltip"), transform=lambda size: f"Current size: {size}"
        )
        self.button_show_send_dialog.on_click(self._button_on_click)
        self.button_clear.on_click(self._button_on_click)

    def close(self):
        "Cannot close"

    def _add_record(self, record):
        self._records.append(record)
        self.output.push(record.output)

    def _notify_exception(self, msg: str):
        "Create a notification that an error occurred."

        msg_short = msg.split("\n", maxsplit=1)[0]
        if self._log_notify_task:
            # Limit to one notification.
            if not self._log_notify_task.done():
                return
            self._log_notify_task.result().close()
        self._log_notify_task = ipylab.app.notification.notify(
            msg_short,
            type=ipylab.NotificationType.error,
            actions=[
                ipylab.NotifyAction(
                    label="📄",
                    caption="Show object log panel.",
                    callback=self.add_to_shell,
                    keep_open=True,
                )
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
            self.output.clear(wait=False)

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
        output = Output()
        body = VBox([select, search, output])

        def observe(change: dict):
            if change["owner"] is select:
                body.children = [select, search, select.value] if select.value else [select, search]
            elif change["owner"] is search and change["new"] in options:
                select.value = options[change["new"]]

        select.observe(observe, "value")
        search.observe(observe, "value")
        try:
            await ipylab.app.dialog.show_dialog("Send record to console", body=body)
            if select.value:
                await ipylab.app.open_console(
                    objects={"record": select.value}, namespace_name=ipylab.app.active_namespace
                )
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
