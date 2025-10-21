# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import logging
import weakref
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from IPython.core.ultratb import FormattedTB
from ipywidgets import CallbackDispatcher
from typing_extensions import override

import ipylab
from ipylab.common import Fixed

if TYPE_CHECKING:
    from collections.abc import MutableMapping


__all__ = ["IpylabLogHandler", "LogLevel"]


class LogLevel(IntEnum):
    CRITICAL = 50
    ERROR = 40
    WARNING = 30
    INFO = 20
    DEBUG = 10


class ANSIColors(StrEnum):
    # Jupyterlab supports ANSI colours
    # https://jakob-bagterp.github.io/colorist-for-python/ansi-escape-codes/standard-16-colors/#structure

    reset = "\033[0m"

    black = "\033[30m"
    red = "\033[31m"
    green = "\033[32m"
    yellow = "\033[33m"
    blue = "\033[34m"
    magenta = "\033[35m"
    cyan = "\033[36m"
    white = "\033[37m"
    default = "\033[39m"
    bright_black = "\033[90m"
    bright_red = "\033[91m"
    bright_green = "\033[92m"
    bright_yellow = "\033[93m"
    bright_blue = "\033[94m"
    bright_magenta = "\033[95m"
    bright_cyan = "\033[96m"
    bright_white = "\033[97m"


COLORS = {
    LogLevel.DEBUG: ANSIColors.cyan,
    LogLevel.INFO: ANSIColors.green,
    LogLevel.WARNING: ANSIColors.bright_yellow,
    LogLevel.ERROR: ANSIColors.red,
    LogLevel.CRITICAL: ANSIColors.bright_red,
}


def truncated_repr(obj: Any, maxlen=120, tail="…") -> str:
    "Do truncated string representation of obj."

    rep = obj.repr_log if hasattr(obj, "repr_log") else repr(obj)
    if len(rep) > maxlen:
        return rep[0 : maxlen - len(tail)] + tail
    return rep


class IpylabLoggerAdapter(logging.LoggerAdapter):
    app = Fixed(lambda _: ipylab.App())

    def __init__(self, name: str, owner: Any) -> None:
        logger = logging.getLogger(name)
        if handler := self.app.logging_handler:
            handler._add_logger(logger)
        super().__init__(logger)
        self.owner_ref = weakref.ref(owner)

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        obj = kwargs.pop("obj", None)
        kwargs["extra"] = {"owner": self.owner_ref, "obj": obj}
        return msg, kwargs


class IpylabLogHandler(logging.Handler):
    _loggers: ClassVar[weakref.WeakSet[logging.Logger]] = weakref.WeakSet()
    formatter: IpylabLogFormatter  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(self, level: LogLevel) -> None:
        super().__init__(level)
        self._callbacks = CallbackDispatcher()

    def _add_logger(self, logger: logging.Logger):
        if logger not in self._loggers:
            logger.setLevel(self.level)
            self._loggers.add(logger)
            logger.addHandler(self)

    @override
    def setLevel(self, level: LogLevel) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        level = LogLevel(level)
        super().setLevel(level)
        for logger in self._loggers:
            logger.setLevel(level)

    def emit(self, record) -> None:
        std_ = "stderr" if record.levelno >= LogLevel.ERROR else "stdout"
        record.output = {"output_type": "stream", "name": std_, "text": self.format(record)}
        self._callbacks(record)

    def register_callback(self, callback, *, remove=False) -> None:
        """Register a callback for when a record is emitted.

        The callback will be called with one argument, the record.

        Parameters
        ----------
        remove: bool (optional)
            Set to true to remove the callback from the list of callbacks.
        """
        self._callbacks.register_callback(callback, remove=remove)


class IpylabLogFormatter(logging.Formatter):
    app = Fixed(lambda _: ipylab.App())

    def __init__(self, *, colors: dict[LogLevel, ANSIColors] = COLORS, reset=ANSIColors.reset, **kwargs) -> None:
        """Initialize the formatter with specified format strings."""
        self.colors = colors
        self.reset = reset
        super().__init__(**kwargs)
        self.tb_formatter = FormattedTB()

    def format(self, record: logging.LogRecord) -> str:
        level = LogLevel(record.levelno)
        record.level_symbol = level.name[0]
        record.color = self.colors[level]
        record.reset = self.reset
        record.owner_rep = truncated_repr(self.get_ref(record, "owner"), 120)
        record.obj_rep = truncated_repr(self.get_ref(record, "obj"), 120)
        return super().format(record)

    def get_ref(self, record, key) -> object | None:
        ref = getattr(record, key, None)
        return ref() if key == "owner" and callable(ref) else ref

    def formatException(self, ei) -> str:
        if not ei[0]:
            return ""
        if self.app.logging_handler:
            tbf = self.tb_formatter
            tbf.verbose if self.app.logging_handler.level == LogLevel.DEBUG else tbf.minimal  # noqa: B018
            return tbf.stb2text(tbf.structured_traceback(*ei))  # pyright: ignore[reportArgumentType]
        return super().formatException(ei)
