# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import ipylab

if TYPE_CHECKING:
    from ipywidgets import Widget


__all__ = ["LogLevel", "LogTypes", "LogPayloadType", "LogPayloadText", "LogPayloadHtml", "LogPayloadOutput"]


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

    @classmethod
    def parse(cls, log):
        level = LogLevel.to_level(log["level"])
        match LogTypes(log["type"]):
            case LogTypes.text:
                return LogPayloadText(type=LogTypes.text, level=level, data=log["data"])
            case LogTypes.html:
                return LogPayloadHtml(type=LogTypes.html, level=level, data=log["data"])
            case LogTypes.output:
                raise NotImplementedError
                return LogPayloadOutput(type=LogTypes.output, level=LogLevel(log["level"]), data=log["data"])


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
    data: Widget


LogPayloadType = LogPayloadBase | LogPayloadText | LogPayloadHtml | LogPayloadOutput


class IpylabLogHandler(logging.Handler):
    def __init__(self) -> None:
        ipylab.app.observe(self._observe_app_log_level, "logger_level")
        super().__init__(LogLevel.to_numeric(ipylab.app.logger_level))

    def _observe_app_log_level(self, change: dict):
        self.setLevel(LogLevel.to_numeric(change["new"]))

    def emit(self, record):
        log = LogPayloadText(type=LogTypes.text, level=LogLevel.to_level(record.levelno), data=self.format(record))
        ipylab.app.send_log_message(log)
