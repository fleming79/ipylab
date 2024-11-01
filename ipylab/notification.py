# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

import traitlets
from ipywidgets import TypedTuple, register
from traitlets import Bool, Container, Dict, Instance, Unicode

from ipylab import Connection, NotificationType, Transform, pack
from ipylab._compat.typing import override
from ipylab.common import Obj, TaskHooks, TransformType
from ipylab.ipylab import Ipylab, IpylabBase

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Callable, Iterable
    from typing import Any


__all__ = ["NotificationManager"]


class NotifyAction(TypedDict):
    label: str
    callback: Callable[[], Any]
    display_type: NotRequired[Literal["default", "accent", "warn", "link"]]
    keep_open: NotRequired[bool]
    caption: NotRequired[str]


class ActionConnection(Connection):
    callback = traitlets.Callable()

    info = Dict(help="info about the item")
    auto_dispose = Bool(True).tag(sync=True)


class NotificationConnection(Connection):
    info = Dict(help="info about the item")
    actions: Container[tuple[ActionConnection, ...]] = TypedTuple(trait=Instance(ActionConnection))
    auto_dispose = Bool(True).tag(sync=True)

    def update(
        self,
        message: str,
        type: NotificationType | None = None,  # noqa: A002
        *,
        auto_close: float | Literal[False] | None = None,
        actions: Iterable[NotifyAction | ActionConnection] = (),
    ) -> Task[bool]:
        args = {
            "id": f"{pack(self)}.id",
            "message": message,
            "type": NotificationType(type) if type else None,
            "autoClose": auto_close,
        }
        to_object = ["args.id"]

        async def update():
            async with self.app.notification as n:
                actions_ = [await n._ensure_action(v) for v in actions]  # noqa: SLF001
                if actions_:
                    args["actions"] = list(map(pack, actions_))  # type: ignore
                    to_object.extend(f"options.actions.{i}" for i in range(len(actions_)))
                    for action in actions_:
                        self.close_extras.add(action)
                return await n.operation("update", toObject=to_object, args=args)

        return self.to_task(update())


@register
class NotificationManager(Ipylab):
    """Create new notifications with access to the notification manager as base.

    ref: https://jupyterlab.readthedocs.io/en/stable/extension/ui_helpers.html#notifications
    """

    SINGLE = True

    _model_name = Unicode("NotificationManagerModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "Notification.manager").tag(sync=True)

    connections: Container[tuple[NotificationConnection | ActionConnection, ...]] = TypedTuple(
        trait=Instance(Connection)
    )

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        """Overload this function as required."""
        match operation:
            case "action_callback":
                callback = ActionConnection.get_existing_connection(payload["cid"]).callback
                result = callback()
                while inspect.isawaitable(result):
                    result = await result
                return result
        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def _ensure_action(self, value: ActionConnection | NotifyAction) -> ActionConnection:
        "Create a new action."
        if isinstance(value, ActionConnection):
            async with value:
                return value
        return await self.new_action(**value)  # type: ignore

    def notify(
        self,
        message: str,
        type: NotificationType = NotificationType.default,  # noqa: A002
        *,
        auto_close: float | Literal[False] | None = None,
        actions: Iterable[NotifyAction | ActionConnection] = (),
    ) -> Task[NotificationConnection]:
        """Create a new notification.

        To update a notification use the update method of the returned `NotificationConnection`.

        NotifyAction:
            label: str
            callback: Callable[[], Any]
            display_type: NotRequired[Literal["default", "accent", "warn", "link"]]
            keep_open: NotRequired[bool]
            caption: NotRequired[str]
        """

        options = {"autoClose": auto_close}
        info = {"type": NotificationType(type), "message": message, "options": options}
        hooks: TaskHooks = {
            "add_to_tuple_fwd": [(self, "connections")],
            "trait_add_fwd": [("info", info)],
        }

        async def notify():
            actions_ = [await self._ensure_action(v) for v in actions]
            if actions_:
                options["actions"] = actions_  # type: ignore
            cid = NotificationConnection.to_cid()
            notification: NotificationConnection = await self.operation(
                "notification",
                message=message,
                type=NotificationType(type) if type else None,
                options=options,
                transform={"transform": Transform.connection, "cid": cid},
                toObject=[f"options.actions[{i}]" for i in range(len(actions_))] if actions_ else [],
            )
            return notification

        return self.to_task(notify(), hooks=hooks)

    def new_action(
        self,
        label: str,
        callback: Callable[[], Any],
        display_type: Literal["default", "accent", "warn", "link"] = "default",
        *,
        keep_open: bool = False,
        caption: str = "",
    ) -> Task[ActionConnection]:
        "Create an action to use in a notification."
        cid = ActionConnection.to_cid()
        info = {"label": label, "displayType": display_type, "keep_open": keep_open, "caption": caption}
        transform: TransformType = {"transform": Transform.connection, "cid": cid}
        hooks: TaskHooks = {
            "trait_add_fwd": [("callback", callback), ("info", info)],
            "add_to_tuple_fwd": [(self, "connections")],
            "close_with_fwd": [self],
        }
        return self.operation("createAction", cid=cid, transform=transform, hooks=hooks, **info)
