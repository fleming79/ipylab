# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
from typing import NotRequired, TypedDict

from IPython.core import completer as IPC  # noqa: N812
from ipywidgets import DOMWidget, ValueWidget, register
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


class IpylabCompleter(IPC.IPCompleter):
    @default("disable_matchers")
    def _default_disable_matchers(self):
        return [
            "IPCompleter.latex_name_matcher",
            "IPCompleter.unicode_name_matcher",
            "back_latex_name_matcher",
            "back_unicode_name_matcher",
            "IPCompleter.fwd_unicode_matcher",
            "IPCompleter.magic_config_matcher",
            "IPCompleter.magic_color_matcher",
            "IPCompleter.magic_matcher",
            "IPCompleter.file_matcher",
        ]

    def do_complete(self, code: str, cursor_pos: int):
        """Completions provided by IPython completer, using Jedi for different namespaces."""
        # Adapted from IPython Shell._get_completions_experimental
        matches = []
        comps = []
        with IPC.provisionalcompleter():
            completions_ = list(self.completions(code, cursor_pos))
            if completions_:
                new_start = min(c.start for c in completions_)
                new_end = max(c.end for c in completions_)
                for c in completions_:
                    comp = IPC.Completion(
                        new_start,
                        new_end,
                        code[new_start : c.start] + c.text + code[c.end : new_end],
                        type=c.type,
                        _origin=c._origin,  # noqa: SLF001
                        signature=c.signature,
                    )
                    matches.append(comp.text)
                    comps.append(
                        {
                            "start": comp.start,
                            "end": comp.end,
                            "text": comp.text,
                            "type": comp.type,
                            "signature": comp.signature,
                        }
                    )
        return {
            "matches": matches,
            "cursor_start": comps[0]["start"] if comps else cursor_pos,
            "cursor_end": comps[0]["end"] if comps else cursor_pos,
            "metadata": {"_jupyter_types_experimental": comps},
            "status": "ok",
        }


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
class CodeEditor(Ipylab, DOMWidget, ValueWidget):
    """A Widget for code editing.

    Code completion is provided for Python code for the specified namespace.
    The default namespace '' corresponds to the shell namespace.

    The completer is invoked with `Tab` by default. Use completer_invoke_keys to change.

    `evaluate` and `do_complete` can be overloaded as required.
    Adjust `completer.disable_matchers` as required.
    """

    _model_name = Unicode("CodeEditorModel").tag(sync=True)
    _view_name = Unicode("CodeEditorView").tag(sync=True)

    value = Unicode().tag(sync=True)
    mime_type = Unicode("text/plain", help="syntax style").tag(sync=True)
    key_bindings = Dict().tag(sync=True)
    editor_options: Instance[CodeEditorOptions] = Dict().tag(sync=True)  # type: ignore

    completer = Instance(IpylabCompleter, ())

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
                return self.do_complete(payload["code"], payload["cursor_pos"])  # type: ignore
            case "evaluateCode":
                await self.evaluate(payload["code"])
                return True

        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def evaluate_code(self, code: str):
        code = code or self.value
        ns = ipylab.app.get_namespace(self.namespace_id)
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

    def _do_complete(self, code: str, cursor_pos: int):
        """Handle a completion request."""
        self.completer.namespace = ipylab.app.get_namespace(self.namespace_id)
        return self.completer.do_complete(code, cursor_pos)
