# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
from typing import NotRequired, TypedDict

from ipywidgets import DOMWidget, register
from traitlets import Callable, Dict, Instance, Unicode, default

import ipylab
from ipylab._compat.typing import override
from ipylab.ipylab import Ipylab

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
class CodeEditor(Ipylab, DOMWidget):
    """A Widget for code editing.

    Code completion is provided for Python code for the specified namespace.
    The default namespace '' corresponds to the shell namespace.

    The completer is invoked with `Tab` by default. Use completer_invoke_keys to change.

    `evaluate` and `do_complete` can be overloaded as required.
    """

    # TODO: connect code completion
    _model_name = Unicode("CodeEditorModel").tag(sync=True)
    _view_name = Unicode("CodeEditorView").tag(sync=True)

    value = Unicode().tag(sync=True)
    mime_type = Unicode("text/plain", help="syntax style").tag(sync=True)
    key_bindings = Dict().tag(sync=True)
    editor_options: Instance[CodeEditorOptions] = Dict().tag(sync=True)  # type: ignore

    namespace_id = Unicode("")
    evaluate = Callable()
    do_complete = Callable()

    @default("key_bindings")
    def _default_key_bindings(self):
        # default is {"invoke_completer": ["Tab"], "evaluate": ["Shift Enter"]}
        return ipylab.plugin_manager.hook.default_editor_key_bindings(app=ipylab.app, obj=self)

    @default("evaluate")
    def _default_evaluate(self):
        return self.evaluate_code

    @default("do_complete")
    def _default_complete_request(self):
        return self._do_complete

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        match operation:
            case "requestComplete":
                return await self.do_complete(payload["code"], payload["cursor_pos"])  # type: ignore
            case "evaluateCode":
                await self.evaluate(payload["code"] or self.value, self.namespace_id)
                return True

        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def evaluate_code(self, code: str, namespace_id: str):
        ns = ipylab.app.get_namespace(namespace_id)
        wait = code.startswith("await")
        try:
            result = eval(code.removeprefix("await").strip(), ns)  # noqa: S307
            if wait or inspect.iscoroutine(result):
                result = await result
        except SyntaxError:
            exec(code, ns, ns)  # noqa: S102
            return next(reversed(ns.values()))
        else:
            return result

    async def _do_complete(self, code: str, cursor_pos: int):
        """Handle a completion request."""
        return ipylab.app._do_complete(self.namespace_id, code, cursor_pos)  # noqa: SLF001
