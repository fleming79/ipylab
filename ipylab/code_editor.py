# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

import anyio
import async_kernel
import traitlets
from ipywidgets import Layout, register, widget_serialization
from ipywidgets.widgets.trait_types import InstanceDict
from ipywidgets.widgets.widget_description import DescriptionStyle
from ipywidgets.widgets.widget_string import _String
from traitlets import Dict, Int, TraitType, Unicode, default, observe
from typing_extensions import override

from ipylab.common import HasSubshell
from ipylab.ipylab import Ipylab

if TYPE_CHECKING:
    __all__ = ["CodeEditor", "CodeEditorOptions"]

mime_types = (
    "text/plain",
    "text/x-python",
    "text/x-ipython",
    "text/x-markdown",
    "text/html",
    "text/css",
    "text/csv",
    "text/yaml",
    "text/json",
    "application/json",
)


class CodeEditorOptions(TypedDict):
    autoClosingBrackets: NotRequired[bool]  # False
    codeFolding: NotRequired[bool]  # False
    cursorBlinkRate: NotRequired[int]  # 1200
    highlightActiveLine: NotRequired[bool]  # False
    highlightSpecialCharacters: NotRequired[bool]  # True
    highlightTrailingWhitespace: NotRequired[bool]  # False
    highlightWhitespace: NotRequired[bool]  # False
    indentUnit: NotRequired[int]  # 4
    lineNumbers: NotRequired[bool]  # True
    lineWrap: NotRequired[bool]  # False
    matchBrackets: NotRequired[bool]  # False
    readOnly: NotRequired[bool]  # False
    rulers: NotRequired[list[int]]
    scrollPastEnd: NotRequired[bool]  # False
    tabFocusable: NotRequired[bool]  # True


@register
class CodeEditor(Ipylab, HasSubshell, _String):
    """A Widget for code editing.

    The entire value is sent as a custom message between frontend and backend.
    The backend (Python) version is assumed to be the correct version in the event
    of overlapping messages.

    Code completion is provided for Python code for the specified namespace.
    The default namespace '' corresponds to the shell namespace.

    The completer is invoked with `Tab` by default. Use completer_invoke_keys to change.

    `evaluate` and `load_value` can be overloaded as required.
    Adjust `completer.disable_matchers` as required.
    """

    _model_name = Unicode("CodeEditorModel").tag(sync=True)
    _view_name = Unicode("CodeEditorView").tag(sync=True)
    _sync = Int(0).tag(sync=True)
    style = InstanceDict(DescriptionStyle, help="Styling customizations").tag(sync=True, **widget_serialization)
    mime_type = Unicode("text/plain", help="syntax style").tag(sync=True)

    key_bindings = Dict().tag(sync=True)
    editor_options: TraitType[CodeEditorOptions, CodeEditorOptions] = Dict().tag(sync=True)  # pyright: ignore[reportAssignmentType]
    update_throttle_ms = Int(100, help="The limit at which changes are synchronised").tag(sync=True)

    layout = InstanceDict(Layout, kw={"overflow": "hidden"}).tag(sync=True, **widget_serialization)
    placeholder = None  # Presently not available

    value = Unicode()
    _setting_value = False
    _sending = False
    evaluate = traitlets.Callable()

    @default("key_bindings")
    def _default_key_bindings(self) -> dict[str, list[str]]:
        return {
            "invoke_completer": ["Tab"],
            "invoke_tooltip": ["Shift Tab"],
            "evaluate": ["Shift Enter"],
            "undo": ["Ctrl Z"],
            "redo": ["Ctrl Shift Z"],
        }

    @default("evaluate")
    def _default_evaluate(self):
        return self.evaluate_builtin

    @observe("value")
    def _observe_value(self, change):
        if self._setting_value != change["new"]:
            # We use throttling to ensure there isn't a backlog of changes to synchronise.
            # When the value is set in Python, we the shared model in the frontend should exactly reflect it.
            self.app.caller.queue_call(self._send_value, change["new"])

    async def _send_value(self, value: str) -> None:
        await anyio.sleep(self.update_throttle_ms / 1e3)
        if value == self.value:
            await self.operation("setValue", {"value": value})
            self._sync = self._sync + 1

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        with async_kernel.utils.subshell_context(self.subshell_id):
            match operation:
                case "requestComplete":
                    return await self.app.kernel.do_complete(**payload)
                case "requestInspect":
                    return await self.app.kernel.do_inspect(**payload)
                case "evaluateCode":
                    return await self.evaluate(payload["code"])
                    return True
                case "setValue":
                    # Only set the value when a valid sync is provided
                    # sync is done
                    if payload["sync"] == self._sync:
                        self._setting_value = payload["value"]
                        try:
                            self.load_value(payload["value"])
                        finally:
                            self._setting_value = False
                    return self.value == payload["value"]

        return await super()._do_operation_for_frontend(operation, payload, buffers)

    def load_value(self, value) -> None:
        "Load the value - overload as required."
        self.value = value

    async def evaluate_builtin(self, code: str = "", *, console=True, objects: dict | None = None) -> None:
        "Evalue code - overload as required."
        with async_kernel.utils.subshell_context(self.subshell_id):
            if objects is not None:
                self.app.kernel.shell.user_ns.update(objects)
            if console:
                cc = await self.app.shell.open_console(subshell_id=self.subshell_id)
                await cc.inject(code or self.value)
            else:
                await self.app.kernel.do_execute(code=code or self.value, silent=True)

    async def clear_undo_history(self) -> None:
        ""
        await self.operation("clearUndoHistory")
