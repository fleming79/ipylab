# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from ipywidgets import DOMWidget, TypedTuple, register
from traitlets import Unicode

from ipylab.ipylab import WidgetBase


@register
class CodeEditor(DOMWidget, WidgetBase):
    "A Widget for code editing."

    # TODO: connect code completion
    _model_name = Unicode("CodeEditorModel").tag(sync=True)
    _view_name = Unicode("CodeEditorView").tag(sync=True)

    value = Unicode().tag(sync=True)
    mime_type = Unicode("text/x-python", help="syntax style").tag(sync=True)
    mime_types = TypedTuple(
        trait=Unicode(),
        default_value=(
            "text/x-python",
            "text/x-ipython",
            "text/x-markdown",
            "application/json",
            "text/html",
            "text/css",
        ),
        help="A list of available mimeTypes",  # TODO: add more types dynamically in the frontend
    ).tag(sync=True)
