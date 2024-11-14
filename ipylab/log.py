# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import collections
import logging
import weakref
from asyncio import Task
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from ipywidgets import HTML, Button, Combobox, HBox, Output, Select, dlink

import ipylab
from ipylab.common import truncated_repr

if TYPE_CHECKING:
    from typing import ClassVar

    from ipylab.ipylab import Ipylab


__all__ = [
    "LogLevel",
    "LogTypes",
    "LogPayloadType",
    "LogPayloadText",
    "LogPayloadHtml",
    "LogPayloadOutput",
    "IpylabLogHandler",
    "log_name_mappings",
    "show_obj_log_panel",
]

objects = {}
log_objects = collections.deque(maxlen=1000)


class LogLevel(StrEnum):
    "The log levels available in Jupyterlab"

    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"

    @classmethod
    def to_numeric(cls, value: LogLevel | int):
        return log_name_mappings[LogLevel(value)]

    @classmethod
    def to_level(cls, val: LogLevel | int) -> LogLevel:
        if isinstance(val, int):
            if val >= log_name_mappings[LogLevel.critical]:
                return LogLevel.critical
            if val >= log_name_mappings[LogLevel.error]:
                return LogLevel.error
            if val >= log_name_mappings[LogLevel.warning]:
                return LogLevel.warning
            if val >= log_name_mappings[LogLevel.info]:
                return LogLevel.info
            return LogLevel.debug
        return LogLevel(val)


log_name_mappings = {
    LogLevel.debug: 10,
    LogLevel.info: 20,
    LogLevel.warning: 30,
    LogLevel.error: 40,
    LogLevel.critical: 50,
}


class LogTypes(StrEnum):
    text = "text"
    html = "html"
    output = "output"


class OutputBase(TypedDict):
    output_type: Literal["update_display_data", "error", "stream"]


class OutputDisplayData(OutputBase):
    output_type: Literal["update_display_data"]
    data: dict[str, str | dict]  # mime-type keyed dictionary of data


class OutputStream(OutputBase):
    output_type: Literal["stream"]
    type: Literal["stdout", "stderr"]
    text: str


class OutputError(OutputBase):
    output_type: Literal["error"]
    ename: str
    evalue: str
    traceback: list[str] | None


OutputTypes = OutputDisplayData | OutputStream | OutputError


class LogPayloadBase(TypedDict):
    type: LogTypes
    level: LogLevel | int
    data: Any


class LogPayloadText(LogPayloadBase):
    type: Literal[LogTypes.text]
    data: str


class LogPayloadHtml(LogPayloadText):
    type: Literal[LogTypes.html]


class LogPayloadOutput(LogPayloadBase):
    type: Literal[LogTypes.output]
    data: OutputTypes


LogPayloadType = LogPayloadBase | LogPayloadText | LogPayloadHtml | LogPayloadOutput


class IpylabLogHandler(logging.Handler):
    _loggers: ClassVar[weakref.WeakSet[logging.Logger]] = weakref.WeakSet()

    def __init__(self) -> None:
        ipylab.app.observe(self._observe_app_log_level, "logger_level")
        super().__init__(LogLevel.to_numeric(ipylab.app.logger_level))

    def _observe_app_log_level(self, change: dict):
        level = LogLevel.to_numeric(change["new"])
        self.setLevel(level)
        for log in self._loggers:
            log.setLevel(level)

    def emit(self, record):
        msg = self.format(record)
        type_ = "stdout" if record.levelno < log_name_mappings[LogLevel.error] else "stderr"
        data = OutputStream(output_type="stream", type=type_, text=msg)
        log = LogPayloadOutput(type=LogTypes.output, level=LogLevel.to_level(record.levelno), data=data)
        ipylab.app.send_log_message(log)

    def set_as_handler(self, log: logging.Logger):
        "Set this handler as a handler for log and keep the level in sync."
        if log not in self._loggers:
            log.addHandler(self)
            log.setLevel(self.level)
            self._loggers.add(log)


class IpylabLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # In addition to formatting, we also make the objects available for the viewer.
        # And substitute the 'owner' and
        owner = getattr(record, "owner", None)
        obj = getattr(record, "obj", None)
        record.owner = truncated_repr(owner, 60)
        record.obj = truncated_repr(obj, 80)
        msg = super().format(record).strip()
        show = bool(record.exc_info)
        if obj or show:
            notify_log_message(owner, obj, msg, show=bool(record.exc_info))
        return msg

    def formatException(self, ei) -> str:  # noqa: N802
        (etype, value, tb) = ei
        sh = ipylab.app._ipy_shell  # noqa: SLF001
        if not sh:
            return super().formatException(ei)
        itb = sh.InteractiveTB
        itb.verbose if ipylab.app.logging_handler.level <= log_name_mappings[LogLevel.debug] else itb.minimal
        stb = itb.structured_traceback(etype, value, tb)  # type: ignore
        return itb.stb2text(stb)


def notify_log_message(owner: ipylab.Ipylab | None, obj: Any, msg: str, *, show=False):
    "Create a notification that an error occurred."

    msg_short = datetime.now().strftime("%H:%M:%S") + " " + msg.split("\n", maxsplit=1)[0]  # noqa: DTZ005
    log_objects.appendleft((msg_short, msg, owner, obj))
    task = objects.get("log_notify_task")
    if isinstance(task, Task):
        # Limit to one notification.
        if not task.done():
            return
        task.result().close()
    if show or not objects.get("log objects"):
        objects["log_notify_task"] = ipylab.app.notification.notify(
            msg_short,
            type=ipylab.NotificationType.error,
            actions=[
                ipylab.NotifyAction(
                    label="📄", caption="Show object log panel.", callback=show_obj_log_panel, keep_open=True
                )
            ],
        )


def show_obj_log_panel():
    "Show a panel that maps a log message to an object."
    key = "log panel"
    if key not in objects:

        class ObjViewer(ipylab.Panel):
            "A simple object viewer to map the message to the object and can put the object in the console."

            def __init__(self):
                self.vpath = HTML(
                    f"<b>Vpath: {ipylab.app.vpath}</b>",
                    tooltip="Use this panel to access the log console from either:\n"
                    "1. The icon in the status bar, or,\n"
                    "2. The context menu (right click).\n"
                    "The controls below are provided to put an object into a console.\n"
                    "Note: Jupyterlab loads a different 'log console'  for the 'console'.",
                )
                self.select_objs = Select(
                    tooltip="Most recent exception is last",
                    layout={"flex": "2 1 auto", "width": "auto", "height": "max-content"},
                )
                self.search = Combobox(
                    placeholder="Search",
                    tooltip="Search for a log entry or object.",
                    ensure_option=True,
                    layout={"width": "auto"},
                )
                self.button_add_to_console = Button(
                    description="Send object and owner to console",
                    tooltip="Add the object and owner to the console. as obj and owner respectively"
                    "\nTip: use the context menu of this pane to access log console.",
                    layout={"width": "50%", "min_width": "content"},
                )
                self.button_refresh = Button(
                    description="Refresh",
                    tooltip="Refresh list of objects",
                    layout={"width": "auto"},
                )
                self.box_controls = HBox(
                    [self.vpath, self.button_add_to_console, self.button_refresh],
                    layout={"flex": "0 0 auto", "justify_content": "space-between", "height": "max-content"},
                )
                layout = {"justify_content": "center", "padding": "20px"}
                self.title.label = "Object log panel"
                self.out = Output(layout={"flex": "1 0 auto"})
                super().__init__(
                    children=[self.box_controls, self.select_objs, self.search, self.out],
                    layout=layout,
                )

                dlink((self.select_objs, "options"), (self.search, "options"))
                dlink(
                    (self.select_objs, "value"),
                    (self.button_add_to_console, "disabled"),
                    transform=lambda value: not value,
                )
                self.button_add_to_console.on_click(self.on_click)
                self.button_refresh.on_click(self.on_click)
                self.select_objs.observe(self._observe, "value")
                self.search.observe(self._observe, "value")

            def _observe(self, change: dict):
                if change["owner"] is self.select_objs:
                    with self.out.hold_trait_notifications():
                        self.out.clear_output(wait=True)
                        self.out.outputs = ()
                        row = self.row
                        self.out.append_stdout(row[1])
                        if owner := row[2]:
                            self.out.append_display_data(owner)
                        if obj := row[3]:
                            self.out.append_display_data(obj)
                if change["owner"] is self.search and self.search.value:
                    self.select_objs.value = self.search.value
                    self.search.value = ""

            def on_click(self, b: Button):
                if b is self.button_add_to_console and self.select_objs.index is not None:
                    objs = {"owner": self.row[2], "obj": self.row[3]}
                    ipylab.app.open_console(objects=objs, namespace_name=ipylab.app.active_namespace)
                if b is self.button_refresh:
                    self.show()

            @property
            def row(self) -> tuple[str, str, Ipylab | None, Any]:
                if self.select_objs.index is None:
                    return "No selection", "", None, None
                return self.data[self.select_objs.index]

            def show(self):
                self.data = tuple(log_objects)
                self.select_objs.value = None
                self.select_objs.options = tuple(v[0] for v in self.data)
                if self.select_objs:
                    self.select_objs.value = self.select_objs.options[0]
                self.add_to_shell(mode=ipylab.InsertMode.split_bottom)

        objects[key] = viewer = ObjViewer()
        viewer.observe(lambda _: objects.pop(key) if objects.get(key) is viewer else None, "comm")
    objects[key].show()
