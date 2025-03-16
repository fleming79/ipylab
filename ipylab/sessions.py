# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING

from traitlets import Unicode

from ipylab.common import Obj, Singular
from ipylab.ipylab import Ipylab, IpylabBase

if TYPE_CHECKING:
    from asyncio import Task


class SessionManager(Singular, Ipylab):
    """
    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html
    """

    _model_name = Unicode("SessionManagerModel", help="Name of the model.", read_only=True).tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app.serviceManager.sessions").tag(sync=True)

    def get_running(self, *, refresh=True) -> Task[dict]:
        "Get a dict of running sessions."
        return self.operation("getRunning", {"refresh": refresh})

    def get_current(self):
        "Get the session of the current widget in the shell."
        return self.operation("getCurrentSession")

    def stop_if_needed(self, path):
        """
        https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html#stopIfNeeded
        """
        return self.execute_method("stopIfNeeded", path)
