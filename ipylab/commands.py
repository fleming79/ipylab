# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from traitlets import Dict, Tuple, Unicode

from ipylab.asyncwidget import AsyncWidgetBase, TransformMode, pack, register
from ipylab.hookspecs import pm

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable

    from ipylab.widgets import Icon


@register
class CommandPalette(AsyncWidgetBase):
    _model_name = Unicode("CommandPaletteModel").tag(sync=True)
    items = Tuple(read_only=True).tag(sync=True)

    def add_item(self, command_id: str, category: str, *, rank=None, args: dict | None = None, **kwgs) -> asyncio.Task:
        return self.schedule_operation(
            operation="addItem", id=command_id, category=category, rank=rank, args=args, **kwgs
        )

    def remove_item(self, command_id: str, category) -> asyncio.Task:
        return self.schedule_operation(operation="removeItem", id=command_id, category=category)


@register
class Launcher(CommandPalette):
    _model_name = Unicode("LauncherModel").tag(sync=True)


@register
class CommandRegistry(AsyncWidgetBase):
    _model_name = Unicode("CommandRegistryModel").tag(sync=True)
    SINGLETON = True
    commands = Tuple(read_only=True).tag(sync=True)
    _execute_callbacks: Dict[str, Callable[[], None]] = Dict()

    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list) -> Any:
        match operation:
            case "execute":
                command_id: str = payload.get("id")  # type:ignore
                cmd = self._get_command(command_id)
                kwgs = payload.get("kwgs") or {} | {"buffers": buffers}
                for k in set(kwgs).difference(inspect.signature(cmd).parameters.keys()):
                    kwgs.pop(k)
                result = cmd(**kwgs)
                if inspect.isawaitable(result):
                    return await result
                return result
            case _:
                pm.hook.unhandled_frontend_operation_message(obj=self, operation=operation)
        raise NotImplementedError

    def _get_command(self, command_id: str) -> Callable:
        "Get a registered Python command"
        if command_id not in self._execute_callbacks:
            msg = f"{command_id} is not a registered command!"
            raise KeyError(msg)
        return self._execute_callbacks[command_id]

    def addPythonCommand(
        self,
        command_id: str,
        execute: Callable,
        *,
        caption="",
        label="",
        icon_class="",
        icon: Icon | None = None,
        command_result_transform: TransformMode = TransformMode.raw,
        **kwgs,
    ):
        # TODO: support other parameters (isEnabled, isVisible...)
        self._execute_callbacks = self._execute_callbacks | {command_id: execute}
        return self.schedule_operation(
            "addPythonCommand",
            id=command_id,
            caption=caption,
            label=label,
            iconClass=icon_class,
            icon=pack(icon),
            command_result_transform=command_result_transform,
            **kwgs,
        )

    def removePythonCommand(self, command_id: str, **kwgs) -> asyncio.Task:
        # TODO: check whether to keep this method, or return disposables like in lab
        if command_id not in self._execute_callbacks:
            msg = f"{command_id=} is not a registered command!"
            raise ValueError(msg)

        def callback(content: dict, payload: list):  # noqa: ARG001
            self._execute_callbacks.pop(command_id, None)

        return self.schedule_operation("removePythonCommand", command_id=command_id, callback=callback, **kwgs)
