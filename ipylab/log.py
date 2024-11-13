# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import logging
import weakref
from asyncio import Task
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from ipywidgets import HTML, Button, Combobox, HBox, Select, dlink

import ipylab
from ipylab.common import truncated_repr
from ipylab.notification import NotifyAction

if TYPE_CHECKING:
    from typing import ClassVar


__all__ = [
    "LogLevel",
    "LogTypes",
    "LogPayloadType",
    "LogPayloadText",
    "LogPayloadHtml",
    "LogPayloadOutput",
    "IpylabLogHandler",
    "log_name_mappings",
    "notify_error",
    "show_error_panel",
]

objects = {}


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
        data = OutputStream(output_type="stream", type="stdout", text=msg)
        log = LogPayloadOutput(type=LogTypes.output, level=LogLevel.to_level(record.levelno), data=data)
        ipylab.app.send_log_message(log)

    def set_as_handler(self, log: logging.Logger):
        "Set this handler as a handler for log and keep the level in sync."
        if log not in self._loggers:
            log.addHandler(self)
            log.setLevel(self.level)
            self._loggers.add(log)


class IpylabLogFormatter(logging.Formatter):
    def formatException(self, ei) -> str:  # noqa: N802
        (etype, value, tb) = ei
        sh = ipylab.app._ipy_shell  # noqa: SLF001
        if not sh:
            return super().formatException(ei)
        itb = sh.InteractiveTB
        itb.verbose if ipylab.app.logging_handler.level <= log_name_mappings[LogLevel.debug] else itb.minimal
        stb = itb.structured_traceback(etype, value, tb)  # type: ignore
        return itb.stb2text(stb)

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if record.exc_info and (e := record.exc_info[1]) and (obj := getattr(record, "obj", None)):
            notify_error(obj, e, msg)
        return msg


def notify_error(obj: ipylab.Ipylab, error: BaseException, msg: str):
    "Create a notification that an error occurred."
    if "error_objects" not in objects:
        objects["error objects"] = weakref.WeakValueDictionary()
    message = f"{truncated_repr(ipylab.app.vpath)}: {truncated_repr(error, 100)} "
    objects["error objects"][f'{truncated_repr(obj)}→{truncated_repr(msg, 60)} {truncated_repr(error, 100)} "'] = obj
    task = objects.get("error_task")
    if isinstance(task, Task):
        # Limit to one notification.
        if not task.done():
            return
        task.result().close()
    a = NotifyAction(label="📄", caption="Show error panel.", callback=show_error_panel, keep_open=True)
    objects["error_task"] = ipylab.app.notification.notify(message, type=ipylab.NotificationType.error, actions=[a])


def show_error_panel():
    "Show an error panel making it possible to view the `log console` and push objects to the `console`."
    if "error_panel" not in objects:
        header = HTML(
            f"<h3>Vpath: {ipylab.app.vpath}</h3>",
            tooltip="Use this panel to access the log console from either\n"
            "1. The icon in the status bar, or,\n"
            "2. The context menu (right click).\n"
            "The controls below are provided to put an object into a console.\n"
            "Note: Jupyterlab loads a different 'log console'  for the 'console'.",
        )
        select_objs = objects["select_objects"] = Select(layout={"width": "auto", "height": "80%"})
        obj_name = Combobox(
            placeholder="Name to use in console ['obj'])",
            options=[f"ojb_{i}" for i in range(10)],
            layout={"flex": "1 0 auto"},
        )
        objects["namespace"] = namespace = Combobox(
            placeholder="Namespace ['']",
            layout={"flex": "1 0 auto"},
        )
        button_add_to_console = Button(
            description="Add to console",
            tooltip="Add an object to the console.\nTip: use the context menu of this pane to access log console.",
            layout={"width": "auto"},
        )
        controls = HBox([obj_name, namespace, button_add_to_console], layout={"height": "80px"})
        objects["error_panel"] = error_panel = ipylab.Panel(
            [header, select_objs, controls],
            layout={"justify_content": "space-between", "padding": "20px"},
        )
        error_panel.title.label = "Error panel"
        dlink((obj_name, "value"), (button_add_to_console, "disabled"), transform=lambda value: not value)

        def on_click(_):
            if obj := objects["error objects"].get(select_objs.value):
                ipylab.app.open_console(objects={obj_name.value or "obj": obj}, namespace_name=namespace.value)
            else:
                show_error_panel()

        button_add_to_console.on_click(on_click)
        objects["select_objects"].options = tuple(reversed(list(objects.get("error objects", []))))
    objects["namespace"].options = tuple(ipylab.app.namespaces)
    objects["error_panel"].add_to_shell(mode=ipylab.InsertMode.split_bottom)
