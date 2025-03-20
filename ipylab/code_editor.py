# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import inspect
import typing
from asyncio import Task
from typing import TYPE_CHECKING, Any, NotRequired, Self, TypedDict, override

from IPython.core import completer as IPC  # noqa: N812
from IPython.utils.tokenutil import token_at_cursor
from ipywidgets import Layout, register, widget_serialization
from ipywidgets.widgets.trait_types import InstanceDict
from ipywidgets.widgets.widget_description import DescriptionStyle
from ipywidgets.widgets.widget_string import _String
from traitlets import Callable, Container, Dict, Instance, Int, Unicode, default, observe

import ipylab
from ipylab.common import Fixed, LastUpdatedDict
from ipylab.ipylab import Ipylab

if TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell

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


class IpylabCompleter(IPC.IPCompleter):
    code_editor: Instance[CodeEditor] = Instance("ipylab.CodeEditor")
    app = Fixed(lambda _: ipylab.App())
    if TYPE_CHECKING:
        shell: InteractiveShell  # Set in IPV.IPCompleter.__init__
        namespace: LastUpdatedDict

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

    def update_namespace(self):
        self.namespace = self.app.get_namespace(self.code_editor.namespace_id)

    def do_complete(self, code: str, cursor_pos: int):
        """Completions provided by IPython completer, using Jedi for different namespaces."""
        # Adapted from IPython Shell._get_completions_experimental
        self.update_namespace()
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

    def _object_inspect_mime(self, oname: str, detail_level=0, omit_sections=()):
        """Get object info as a mimebundle of formatted representations.

        A mimebundle is a dictionary, keyed by mime-type.
        It must always have the key `'text/plain'`.
        """
        # Extracted from ipykernel Shell
        # Required to specify the namespace
        self.update_namespace()
        namespaces = ((self.code_editor.namespace_id, self.namespace),)
        with self.shell.builtin_trap:
            info = self.shell._object_find(oname, namespaces)  # noqa: SLF001
            if info.found:
                return self.shell.inspector._get_info(  # noqa: SLF001
                    info.obj,
                    oname,
                    info=info,
                    detail_level=detail_level,
                    formatter=None,
                    omit_sections=omit_sections,
                )
            raise KeyError(oname)

    def do_inspect(self, code, cursor_pos, detail_level=0, omit_sections=()):
        """Handle code inspection."""
        name = token_at_cursor(code, cursor_pos)

        reply_content: dict[str, Any] = {"status": "ok"}
        reply_content["data"] = {}
        reply_content["metadata"] = {}
        try:
            bundle = self._object_inspect_mime(name, detail_level=detail_level, omit_sections=omit_sections)
            reply_content["data"].update(bundle)
            if not self.shell.enable_html_pager:
                reply_content["data"].pop("text/html")
            reply_content["found"] = True
        except KeyError:
            reply_content["found"] = False
        return reply_content

    async def evaluate(self, code: str):
        """Evaluate code in the code editor namespace."""
        code = code or self.code_editor.value
        self.update_namespace()
        ns = self.namespace
        wait = code.startswith("await")
        try:
            result = eval(code.removeprefix("await").strip(), ns)  # noqa: S307
            if wait or inspect.iscoroutine(result):
                result = await result
            if not self.code_editor.namespace_id:
                self.app.shell.add_objects_to_ipython_namespace(ns)
        except SyntaxError:
            exec(code, ns, ns)  # noqa: S102
            return next(reversed(ns.values()))
        else:
            return result


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
class CodeEditor(Ipylab, _String):
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
    style = InstanceDict(DescriptionStyle, help="Styling customizations").tag(sync=True, **widget_serialization)
    mime_type = Unicode("text/plain", help="syntax style").tag(sync=True)
    key_bindings = Dict().tag(sync=True)
    editor_options: Instance[CodeEditorOptions] = Dict().tag(sync=True)  # type: ignore
    update_throttle_ms = Int(100, help="The limit at which changes are synchronised").tag(sync=True)
    _sync = Int(0).tag(sync=True)

    layout = InstanceDict(Layout, kw={"overflow": "hidden"}).tag(sync=True, **widget_serialization)
    placeholder = None  # Presently not available

    value = Unicode()
    _update_task: None | Task = None
    _setting_value = False
    completer: Fixed[Self, IpylabCompleter] = Fixed(
        lambda c: IpylabCompleter(
            code_editor=c["owner"],
            shell=getattr(getattr(c["owner"].comm, "kernel", None), "shell", None),
            dynamic=["code_editor", "shell"],
        ),
    )
    namespace_id = Unicode("")
    evaluate: Container[typing.Callable[[str], typing.Coroutine]] = Callable()  # type: ignore
    load_value: Container[typing.Callable[[str], None]] = Callable()  # type: ignore

    @default("key_bindings")
    def _default_key_bindings(self):
        return {
            "invoke_completer": ["Tab"],
            "invoke_tooltip": ["Shift Tab"],
            "evaluate": ["Shift Enter"],
            "undo": ["Ctrl Z"],
            "redo": ["Ctrl Shift Z"],
        }

    @default("evaluate")
    def _default_evaluate(self):
        return self.completer.evaluate

    @default("load_value")
    def _default_load_value(self):
        return lambda value: self.set_trait("value", value)

    @observe("value")
    def _observe_value(self, _):
        if not self._setting_value and not self._update_task:
            # We use throttling to ensure there isn't a backlog of changes to synchronise.
            # When the value is set in Python, we the shared model in the frontend should exactly reflect it.
            async def send_value():
                try:
                    while True:
                        value = self.value
                        await self.operation("setValue", {"value": value})
                        self._sync = self._sync + 1
                        await asyncio.sleep(self.update_throttle_ms / 1e3)
                        if self.value == value:
                            return
                finally:
                    self._update_task = None

            self._update_task = self.to_task(send_value(), "Send value to frontend")

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        match operation:
            case "requestComplete":
                return self.completer.do_complete(payload["code"], payload["cursor_pos"])  # type: ignore
            case "requestInspect":
                return self.completer.do_inspect(payload["code"], payload["cursor_pos"])  # type: ignore
            case "evaluateCode":
                await self.evaluate(payload["code"])
                return True
            case "setValue":
                if self._update_task:
                    await self._update_task
                # Only set the value when a valid sync is provided
                # sync is done
                if payload["sync"] == self._sync:
                    self._setting_value = True
                    try:
                        self.load_value(payload["value"])
                    finally:
                        self._setting_value = False
                return self.value == payload["value"]

        return await super()._do_operation_for_frontend(operation, payload, buffers)

    def clear_undo_history(self):
        return self.operation("clearUndoHistory")
