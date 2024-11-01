# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
from asyncio import Task
from typing import TYPE_CHECKING, Any

from ipywidgets import Widget

import ipylab
from ipylab.common import ErrorSource, IpylabKwgs, TaskHooks, hookimpl
from ipylab.ipylab import Ipylab
from ipylab.notification import NotifyAction

objects = {}

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from traitlets import HasTraits

    from ipylab import App


def trait_tuple_add(owner: HasTraits, name: str, value: Any):
    items = getattr(owner, name)
    if value not in items:
        owner.set_trait(name, (*items, value))


@hookimpl
def start_app(vpath: str):
    "Default implementation of App and Plugins"
    ipylab.App(vpath=vpath)


@hookimpl
def on_error(obj: Ipylab, source: ErrorSource, error: Exception):
    msg = f"{source} {error}"
    obj.log.exception(msg, extra={"source": source, "error": error})
    task = objects.get("error_task")
    if isinstance(task, Task):
        # Try to minimize the number of notifications.
        if not task.done():
            return
        task.result().close()
    a = NotifyAction(label="📝", caption="Toggle log console", callback=obj.app.toggle_log_console, keep_open=True)
    objects["error_task"] = obj.app.notification.notify(msg, type=ipylab.NotificationType.error, actions=[a])


@hookimpl
def ensure_run(obj: ipylab.Ipylab, aw: Callable | Awaitable | None):
    try:
        if callable(aw):
            try:
                aw = aw(obj)
            except TypeError:
                aw = aw()
        if inspect.iscoroutine(aw):
            obj.to_task(aw, f"Ensure run {aw}")
    except Exception as e:
        obj.on_error(ErrorSource.EnsureRun, e)
        raise
    else:
        return True


@hookimpl
def task_result(obj: Ipylab, result: HasTraits, hooks: TaskHooks):
    # close with
    for owner in hooks.pop("close_with_fwd", ()):
        # Close result with each item.
        if isinstance(owner, Ipylab) and isinstance(result, Widget):
            if not owner.comm:
                result.close()
                raise RuntimeError(str(owner))
            owner.close_extras.add(result)
    for obj_ in hooks.pop("close_with_rev", ()):
        # Close each item with the result.
        if isinstance(result, Ipylab):
            result.close_extras.add(obj_)

    # tuple add
    for owner, name in hooks.pop("add_to_tuple_fwd", ()):
        # Add each item of to tuple of result.
        if isinstance(result, Ipylab):
            result.add_to_tuple(owner, name)
        else:
            trait_tuple_add(owner, name, result)
    for name, value in hooks.pop("add_to_tuple_rev", ()):
        # Add the result the the tuple with 'name' for each item.
        if isinstance(value, Ipylab):
            value.add_to_tuple(result, name)
        else:
            trait_tuple_add(result, name, value)

    # trait add
    for name, value in hooks.pop("trait_add_fwd", ()):
        # Set each trait of result with value.
        if isinstance(value, Ipylab):
            value.add_as_trait(result, name)
        else:
            result.set_trait(name, value)
    for owner, name in hooks.pop("trait_add_rev", ()):
        # Set set trait of each value with result.
        if isinstance(result, Ipylab):
            result.add_as_trait(owner, name)
        else:
            owner.set_trait(name, result)

    for cb in hooks.pop("callbacks", ()):
        ensure_run(obj, cb(result))

    if hooks:
        msg = f"Invalid hooks detected: {hooks}"
        raise ValueError(msg)


@hookimpl
def opening_console(app: App, args: dict, objects: dict, kwgs: IpylabKwgs):
    "no-op"


@hookimpl
def vpath_getter(app: App, kwgs: dict) -> Awaitable[str] | str:
    return app.dialog.get_text(**kwgs)


@hookimpl
def ready(obj: Ipylab):
    "Pass through"
