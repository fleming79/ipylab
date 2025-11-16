# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest
from aiologic.lowlevel import create_async_event
from ipylab import Ipylab
from ipylab.common import (
    LastUpdatedDict,
    Singular,
    Transform,
    TransformDictAdvanced,
    TransformDictConnection,
    TransformDictFunction,
    TransformType,
)
from ipylab.connection import Connection
from traitlets import Unicode
from typing_extensions import override


class CommonTestClass:
    def __init__(self, value=1):
        self.value = value


def test_last_updated_dict():
    d = LastUpdatedDict()
    d["a"] = 1
    d["b"] = 2
    assert list(d.keys()) == ["a", "b"]
    d["a"] = 3
    assert list(d.keys()) == ["b", "a"]

    d = LastUpdatedDict(mode="first")
    d["a"] = 1
    d["b"] = 2
    assert list(d.keys()) == ["b", "a"]
    d["a"] = 3
    assert list(d.keys()) == ["a", "b"]


class TestTransformValidate:
    def test_validate_function_transform(self):
        transform: TransformDictFunction = {
            "transform": Transform.function,
            "code": "function (obj, options) { return obj.id; }",
        }
        result = Transform.validate(transform)
        assert isinstance(result, dict)
        assert result["transform"] == Transform.function
        assert result["code"] == "function (obj, options) { return obj.id; }"

    def test_validate_connection_transform(self):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "connection_id": "ipylab-Connection",
        }
        result = Transform.validate(transform)
        assert isinstance(result, dict)
        assert result["transform"] == Transform.connection
        assert result.get("connection_id") == "ipylab-Connection"

    def test_validate_advanced_transform(self):
        transform: TransformDictAdvanced = {
            "transform": Transform.advanced,
            "mappings": {
                "path1": {
                    "transform": Transform.function,
                    "code": "function (obj, options) { return obj.id; }",
                },
                "path2": {
                    "transform": Transform.connection,
                    "connection_id": "ipylab-Connection",
                },
            },
        }
        result = Transform.validate(transform)
        assert isinstance(result, dict)
        assert result["transform"] == Transform.advanced
        assert "path1" in result["mappings"]
        assert "path2" in result["mappings"]

    def test_validate_invalid_function_transform(self):
        transform: TransformType = {  # pyright: ignore[reportAssignmentType]
            "transform": Transform.function,
            "code": "invalid_code",
        }
        with pytest.raises(TypeError):
            Transform.validate(transform)

    def test_validate_invalid_connection_transform(self):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "connection_id": "--invalid--",
        }
        with pytest.raises(
            ValueError, match="'connection_id' should start with 'ipylab-' but got connection_id='--invalid--'"
        ):
            Transform.validate(transform)

    def test_validate_invalid_advanced_transform(self):
        transform: TransformType = {  # pyright: ignore[reportAssignmentType]
            "transform": Transform.advanced,
            "mappings": "invalid_mappings",
        }
        with pytest.raises(TypeError):
            Transform.validate(transform)

    def test_validate_non_dict_transform(self):
        transform = Transform.auto
        result = Transform.validate(transform)
        assert result == Transform.auto

    def test_validate_invalid_non_dict_transform(self):
        transform = Transform.function
        with pytest.raises(ValueError, match="This type of transform should be passed as a dict"):
            Transform.validate(transform)


class TestTransformPayload:
    async def test_transform_payload_advanced(self, app):
        transform: TransformDictAdvanced = {
            "transform": Transform.advanced,
            "mappings": {
                "key1": {
                    "transform": Transform.function,
                    "code": "function (obj, options) { return obj.id; }",
                },
                "key2": {
                    "transform": Transform.connection,
                    "connection_id": "ipylab-Connection",
                },
            },
        }
        payload = {
            "key1": {"id": "test_id"},
            "key2": {"connection_id": "ipylab-Connection"},
        }
        result = await Transform.transform_payload(transform, payload)
        assert isinstance(result, dict)
        assert "key1" in result
        assert "key2" in result

    async def test_transform_payload_connection(self, app):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "connection_id": "ipylab-Connection",
        }
        payload = {"connection_id": "ipylab-Connection"}
        result = await Transform.transform_payload(transform, payload)
        assert isinstance(result, Connection)

    async def test_transform_payload_auto(self, app):
        transform = Transform.auto
        payload = {"connection_id": "ipylab-Connection"}
        result = await Transform.transform_payload(transform, payload)
        assert isinstance(result, Connection)

    async def test_transform_payload_no_transform(self, app):
        transform = Transform.null
        payload = {"key": "value"}
        result = await Transform.transform_payload(transform, payload)
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
        obj._on_ready("123")
        await obj.ready()
        await anyio.sleep(0.1)
        callback.assert_called()

        callback.reset_mock()
        obj._ready_events["123"] = create_async_event()
        obj._on_ready("123")
        await anyio.sleep(0.1)
        callback.assert_called()

        # Reset the mock and remove the callback
        callback.reset_mock()
        obj.on_ready(callback, remove=True)
        assert callback not in obj._on_ready_callbacks

        # Simulate the ready event again, callback should not be called
        obj._ready_events["123"] = create_async_event()
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
        obj._on_ready("123")
        await anyio.sleep(0.1)
        callback.assert_called()
        await anyio.sleep(0.1)
        assert callback.await_count == 1
        obj.close()
