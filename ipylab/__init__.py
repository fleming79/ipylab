# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from ipylab import common, menu
from ipylab._frontend import module_version as __version__
from ipylab.code_editor import CodeEditor
from ipylab.common import Area, Fixed, InsertMode, Obj, Transform, hookimpl, pack, to_selector
from ipylab.connection import Connection, ShellConnection
from ipylab.ipylab import Ipylab
from ipylab.jupyterfrontend import App, JupyterFrontEnd
from ipylab.notification import NotificationType, NotifyAction
from ipylab.simple_output import SimpleOutput
from ipylab.widgets import Icon, Panel, SplitPanel

__all__ = [
    "__version__",
    "common",
    "CodeEditor",
    "Connection",
    "Fixed",
    "ShellConnection",
    "SimpleOutput",
    "Panel",
    "SplitPanel",
    "Icon",
    "Area",
    "NotificationType",
    "NotifyAction",
    "InsertMode",
    "hookimpl",
    "Transform",
    "pack",
    "_jupyter_labextension_paths",
    "Ipylab",
    "App",
    "Obj",
    "menu",
    "JupyterFrontEnd",
    "to_selector",
]


def _jupyter_labextension_paths():
    "Called by Jupyterlab see: jupyterlab.federated_labextensions._get_labextension_metadata."
    return [{"src": "labextension", "dest": "ipylab"}]


def _get_plugin_manager():
    # Only to be run once here
    import pluggy

    from ipylab import hookspecs, lib

    pm = pluggy.PluginManager("ipylab")
    pm.add_hookspecs(hookspecs)
    pm.register(lib)
    pm.load_setuptools_entrypoints("ipylab")
    return pm


plugin_manager = _get_plugin_manager()
del _get_plugin_manager
