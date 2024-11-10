# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import logging
import weakref
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import ipylab

if TYPE_CHECKING:
    from typing import ClassVar


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
    loggers: ClassVar[weakref.WeakSet[logging.Logger]] = weakref.WeakSet()

    def __init__(self) -> None:
        ipylab.app.observe(self._observe_app_log_level, "logger_level")
        super().__init__(LogLevel.to_numeric(ipylab.app.logger_level))

    def _observe_app_log_level(self, change: dict):
        level = LogLevel.to_numeric(change["new"])
        self.setLevel(level)
        for log in self.loggers:
            log.setLevel(level)

    def emit(self, record):
        log = LogPayloadOutput(
            type=LogTypes.output, level=LogLevel.to_level(record.levelno), data=self.parse_record(record)
        )
        ipylab.app.send_log_message(log)

    def parse_record(self, record) -> OutputTypes:
        msg = self.format(record)
        if record.levelno <= log_name_mappings[LogLevel.warning]:
            return OutputStream(output_type="stream", type="stdout", text=msg)
        if record.exc_info and record.exc_info[2]:
            (etype, value, tb) = record.exc_info
            stb = ipylab.app._ipy_shell.InteractiveTB.structured_traceback(etype, value, tb)  # type: ignore # noqa: SLF001
        else:
            value, stb = "", None
        return OutputError(output_type="error", ename=str(value), evalue=msg, traceback=stb)


class IpylabLoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger: logging.Logger, extra=None):
        logger.setLevel(LogLevel.to_numeric(ipylab.app.logger_level))
        IpylabLogHandler.loggers.add(logger)
        super().__init__(logger, extra)


class IpylabLogFormatter(logging.Formatter):
    def formatException(self, ei) -> str:  # noqa: ARG002, N802
        return ""
