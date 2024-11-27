# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect

from ipywidgets import DOMWidget, register
from traitlets import Dict, Unicode, default

import ipylab
from ipylab._compat.typing import override
from ipylab.ipylab import Ipylab

mime_types = (
    "text/plain",
    "text/x-python",
    "text/x-ipython",
    "text/x-markdown",
    "application/json",
    "text/html",
    "text/css",
)


@register
class CodeEditor(DOMWidget, Ipylab):
    """A Widget for code editing.

    Code completion is provided for Python code for the specified namespace.

    The completer is invoked with `CTRL Space` by default. Use completer_invoke_keys to change.

    """

    # TODO: connect code completion
    _model_name = Unicode("CodeEditorModel").tag(sync=True)
    _view_name = Unicode("CodeEditorView").tag(sync=True)

    value = Unicode().tag(sync=True)
    mime_type = Unicode("text/plain", help="syntax style").tag(sync=True)
    key_bindings = Dict().tag(sync=True)
    namespace_name = Unicode("").tag(sync=True)

    @default("key_bindings")
    def _default_key_bindings(self):
        # default is {"invoke_completer": ["Ctrl Space"], "evaluate": ["Shift Enter"]}
        return ipylab.plugin_manager.hook.default_editor_key_bindings(app=ipylab.app, obj=self)

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        match operation:
            case "requestComplete":
                return await self._complete_request(**payload)
            case "evaluateCode":
                payload["namespace_name"] = self.namespace_name
                if not payload.get("evaluate"):
                    # If there was no selection, we will evaluate all of the code
                    payload["evaluate"] = self.value
                await ipylab.app._evaluate(payload, [])  # noqa: SLF001
                return True

        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def _complete_request(self, code: str, cursor_pos: int):
        """Handle a completion request."""
        ipylab.app.activate_namespace(self.namespace_name)
        matches = self.comm.kernel.do_complete(code, cursor_pos)  # type: ignore
        if inspect.isawaitable(matches):
            matches = await matches
        return matches
