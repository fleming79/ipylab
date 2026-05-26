# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest
from ipylab import Ipylab
from ipylab.common import Singular, Transform, TransformDictConnection
from ipylab.connection import Connection
from traitlets import Unicode
from typing_extensions import override

# pyright: reportPrivateUsage=false


class CommonTestClass:
    def __init__(self, value=1) -> None:  # pyright: ignore[reportMissingSuperCall]
        self.value = value


class TestTransformValidate:
    def test_validate_connection_transform(self):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "connection_id": "ipylab-Connection",
        }
        result = Transform.validate(transform)
        assert isinstance(result, dict)
        assert result["transform"] == Transform.connection
        assert result.get("connection_id") == "ipylab-Connection"

    def test_validate_invalid_connection_transform(self):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "connection_id": "--invalid--",
        }
        with pytest.raises(
            ValueError, match="'connection_id' should start with 'ipylab-' but got connection_id='--invalid--'"
        ):
            Transform.validate(transform)

    def test_validate_non_dict_transform(self):
        transform = Transform.auto
        result = Transform.validate(transform)
        assert result == Transform.auto


class TestTransformPayload:
    async def test_transform_payload_connection(self, app):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "connection_id": "ipylab-Connection",
        }
        payload = {"connection_id": "ipylab-Connection"}
        result = Transform.transform_payload(transform, payload)
        assert isinstance(result, Connection)

    async def test_transform_payload_auto(self, app):
        transform = Transform.auto
        payload = {"connection_id": "ipylab-Connection"}
        result = Transform.transform_payload(transform, payload)
        assert isinstance(result, Connection)

    async def test_transform_payload_no_transform(self, app):
        transform = Transform.null
        payload = {"key": "value"}
        result = Transform.transform_payload(transform, payload)
        assert result == payload


class TestLimited:
    async def test_limited_new_single(self):
        class MySingular(Singular):
            pass

        obj1 = MySingular()
        obj2 = MySingular()
        assert obj1 is obj2
        obj1.close()
        assert obj1 not in obj1._singular_instances
        assert obj1.closed

    async def test_limited_newget_single_keyed(self):
        # Test that the get_single_key method and arguments are passed
        class KeyedSingle(Singular):
            key = Unicode(allow_none=True)

            def __init__(self, /, key: str | None, **kwgs):
                super().__init__(key=key, **kwgs)

            @override
            @classmethod
            def get_single_key(cls, key: str, **kwgs):
                return key

        obj1 = KeyedSingle(key="key1")
        obj2 = KeyedSingle(key="key1")
        obj3 = KeyedSingle(key="key2")
        obj4 = KeyedSingle("key2")
        obj5 = KeyedSingle(None)
        obj6 = KeyedSingle(None)

        assert obj1 in KeyedSingle._singular_instances.values()
        assert obj1 is obj2
        assert obj1 is not obj3
        assert obj4 is obj3
        assert obj5 is not obj6
        assert obj5 not in KeyedSingle._singular_instances.values()


class TestOnReady:
    async def test_on_ready_add_and_remove(self, app):
        obj = Ipylab()
        callback = MagicMock()

        # Add the callback
        obj.on_ready(callback)
        assert callback in obj._on_ready_callbacks

        # Simulate the ready event
        await obj._set_ready()
        await obj.wait_ready()
        await anyio.sleep(0.1)
        callback.assert_called()

        callback.reset_mock()
        await obj._set_ready()
        await anyio.sleep(0.1)
        callback.assert_called()

        # Reset the mock and remove the callback
        callback.reset_mock()
        obj.on_ready(callback, remove=True)
        assert callback not in obj._on_ready_callbacks

        # Simulate the ready event again, callback should not be called
        await anyio.sleep(0.1)
        callback.assert_not_called()

        obj.close()

    async def test_on_ready_async(self, app):
        obj = Ipylab()
        callback = AsyncMock()

        # Add the callback
        obj.on_ready(callback)
        assert callback in obj._on_ready_callbacks

        # Simulate the ready event
        await obj._set_ready()
        await anyio.sleep(0.1)
        callback.assert_called()
        await anyio.sleep(0.1)
        assert callback.await_count == 1
        obj.close()
