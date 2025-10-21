# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from ipylab import common, log, menu, simple_output, widgets
from ipylab._frontend import module_version as __version__
from ipylab.code_editor import CodeEditor
from ipylab.common import (
    Area,
    Fixed,
    InsertMode,
    Obj,
    Transform,
    hookimpl,
    pack,
    to_selector,
)
from ipylab.connection import Connection, ShellConnection
from ipylab.ipylab import Ipylab
from ipylab.jupyterfrontend import App, JupyterFrontEnd
from ipylab.notification import NotificationType, NotifyAction
from ipylab.simple_output import SimpleOutput
from ipylab.widgets import Icon, Panel, SplitPanel

__all__ = [
    "App",
    "Area",
    "CodeEditor",
    "Connection",
    "Fixed",
    "Icon",
    "InsertMode",
    "Ipylab",
    "JupyterFrontEnd",
    "NotificationType",
    "NotifyAction",
    "Obj",
    "Panel",
    "ShellConnection",
    "SimpleOutput",
    "SplitPanel",
    "Transform",
    "__version__",
    "_jupyter_labextension_paths",
    "common",
    "hookimpl",
    "log",
    "menu",
    "pack",
    "simple_output",
    "to_selector",
    "widgets",
]


def _jupyter_labextension_paths():
    "Called by Jupyterlab see: jupyterlab.federated_labextensions._get_labextension_metadata."
    return [{"src": "labextension", "dest": "ipylab"}]


def _get_plugin_manager():
    # Only to be run once here
    import pluggy  # noqa: PLC0415

    from ipylab import hookspecs, lib  # noqa: PLC0415

    pm = pluggy.PluginManager("ipylab")
    pm.add_hookspecs(hookspecs)
    pm.register(lib)
    pm.load_setuptools_entrypoints("ipylab")
    return pm


plugin_manager = _get_plugin_manager()
del _get_plugin_manager
