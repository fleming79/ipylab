# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pluggy

hookspec = pluggy.HookspecMarker("ipylab")

if TYPE_CHECKING:
    from collections.abc import Awaitable

    import ipylab
    from ipylab.log import IpylabLogHandler


@hookspec(firstresult=True)
def launch_ipylab():
    """A hook called to start Jupyterlab.

    This is called by with the shell command `ipylab`.
    """


@hookspec(historic=True)
async def autostart_once(app: ipylab.App) -> None | Awaitable[None]:
    """A hook that is called when the `app` is ready for the first time.

    Historic
    --------

    This plugin is historic so will be called when a plugin is registered if the
    app is already ready.
    """


@hookspec(historic=True)
async def autostart(app: ipylab.App) -> None | Awaitable[None]:
    """A hook that is called when the `app` is ready.

    Historic
    --------

    This plugin is historic so will be called when a plugin is registered if the
    app is already ready.
    """


@hookspec
def default_namespace_objects(namespace_id: str, app: ipylab.App) -> dict[str, Any]:  # type: ignore
    "A hook to specify additional namespace objects when a namespace is loaded."


@hookspec(firstresult=True)
async def vpath_getter(app: ipylab.App, kwgs: dict) -> str:  # type: ignore
    """A hook called during `app.shell.add` when `evaluate` is code and `vpath`
    is passed as a dict.

    This hook provides for dynamic determination of the vpath/kernel to use when
    adding 'evaluate' code to the shell. The default behaviour is prompt the user
    for a path."""


@hookspec(firstresult=True)
def get_logging_handler(app: ipylab.App) -> IpylabLogHandler:  # type: ignore
    "Get the asyncio event loop."
