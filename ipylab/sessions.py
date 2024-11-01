# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from ipylab.common import Obj
from ipylab.ipylab import Ipylab, IpylabBase


class SessionManager(Ipylab):
    """
    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html
    """

    SINGLE = True

    ipylab_base = IpylabBase(Obj.IpylabModel, "app.serviceManager.sessions").tag(sync=True)

    def refresh_running(self):
        """Force a call to refresh running sessions."""
        return self.execute_method("refreshRunning")

    def stop_if_needed(self, path):
        """
        https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html#stopIfNeeded
        """
        return self.execute_method("stopIfNeeded", path)
