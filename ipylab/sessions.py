# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

import asyncio

from ipylab.jupyterfrontend_subsection import JupyterFrontEndSubsection


class SessionManager(JupyterFrontEndSubsection):
    """
    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html
    """

    JFE_JS_SUB_PATH = "sessionManager"

    def refreshRunning(self) -> asyncio.Task:
        """Force a call to refresh running sessions."""
        return self.executeMethod("refreshRunning")

    def stopIfNeeded(self, path) -> asyncio.Task:
        """
        https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html#stopIfNeeded
        """
        return self.executeMethod("stopIfNeeded", path)
