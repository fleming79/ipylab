# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import Self

import pytest
from traitlets import Unicode
from typing_extensions import override

import ipylab
import ipylab.common
from ipylab.common import (
    Fixed,
    FixedCreated,
    LastUpdatedDict,
    Singular,
    Transform,
    TransformDictAdvanced,
    TransformDictConnection,
    TransformDictFunction,
)
from ipylab.connection import Connection


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
            "cid": "ipylab-Connection",
        }
        result = Transform.validate(transform)
        assert isinstance(result, dict)
        assert result["transform"] == Transform.connection
        assert result.get("cid") == "ipylab-Connection"

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
                    "cid": "ipylab-Connection",
                },
            },
        }
        result = Transform.validate(transform)
        assert isinstance(result, dict)
        assert result["transform"] == Transform.advanced
        assert "path1" in result["mappings"]
        assert "path2" in result["mappings"]

    def test_validate_invalid_function_transform(self):
        transform = {
            "transform": Transform.function,
            "code": "invalid_code",
        }
        with pytest.raises(TypeError):
            Transform.validate(transform)  # type: ignore

    def test_validate_invalid_connection_transform(self):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "cid": "invalid_cid",
        }
        with pytest.raises(ValueError, match="'cid' should start with 'ipylab-' but got cid='invalid_cid'"):
            Transform.validate(transform)

    def test_validate_invalid_advanced_transform(self):
        transform = {
            "transform": Transform.advanced,
            "mappings": "invalid_mappings",
        }
        with pytest.raises(TypeError):
            Transform.validate(transform)  # type: ignore

    def test_validate_non_dict_transform(self):
        transform = Transform.auto
        result = Transform.validate(transform)
        assert result == Transform.auto

    def test_validate_invalid_non_dict_transform(self):
        transform = Transform.function
        with pytest.raises(ValueError, match="This type of transform should be passed as a dict.*"):
            Transform.validate(transform)


@pytest.fixture
async def mock_connection(mocker):
    mocker.patch.object(Connection, "_ready")


class TestTransformPayload:
    async def test_transform_payload_advanced(self, mock_connection):
        transform: TransformDictAdvanced = {
            "transform": Transform.advanced,
            "mappings": {
                "key1": {
                    "transform": Transform.function,
                    "code": "function (obj, options) { return obj.id; }",
                },
                "key2": {
                    "transform": Transform.connection,
                    "cid": "ipylab-Connection",
                },
            },
        }
        payload = {
            "key1": {"id": "test_id"},
            "key2": {"cid": "ipylab-Connection"},
        }
        result = await Transform.transform_payload(transform, payload)
        assert isinstance(result, dict)
        assert "key1" in result
        assert "key2" in result

    async def test_transform_payload_connection(self, mock_connection):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "cid": "ipylab-Connection",
        }
        payload = {"cid": "ipylab-Connection"}
        result = await Transform.transform_payload(transform, payload)
        assert isinstance(result, Connection)

    async def test_transform_payload_auto(self, mock_connection):
        transform = Transform.auto
        payload = {"cid": "ipylab-Connection"}
        result = await Transform.transform_payload(transform, payload)
        assert isinstance(result, Connection)

    async def test_transform_payload_no_transform(self, mock_connection):
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


class TestFixed:
    def test_readonly_basic(self):
        class TestOwner:
            test_instance = Fixed(CommonTestClass)

        owner = TestOwner()
        assert isinstance(owner.test_instance, CommonTestClass)
        assert owner.test_instance.value == 1

    def test_readonly_create_function(self, app: ipylab.App):
        class TestOwner:
            app = Fixed(lambda _: ipylab.App())
            app1: Fixed[Self, ipylab.App] = Fixed("ipylab.App")

        owner = TestOwner()
        assert owner.app is app
        assert owner.app1 is app

    def test_readonly_create_invalid(self, app):
        with pytest.raises(TypeError):
            assert Fixed(123)  # type: ignore

    def test_readonly_created_callback_method(self):
        class TestOwner:
            test_instance: Fixed[Self, CommonTestClass] = Fixed(
                lambda _: CommonTestClass(value=300),
                created=lambda c: c["owner"].instance_created(c),
            )

            def instance_created(self, info: FixedCreated):
                assert isinstance(info["obj"], CommonTestClass)
                assert info["obj"].value == 300
                assert info["owner"] is self

        owner = TestOwner()
        assert isinstance(owner.test_instance, CommonTestClass)
        assert owner.test_instance.value == 300

    def test_readonly_forbidden_set(self):
        class TestOwner:
            test_instance = Fixed(CommonTestClass)

        owner = TestOwner()
        with pytest.raises(AttributeError, match="Setting `Fixed` parameter TestOwner.test_instance is forbidden!"):
            owner.test_instance = CommonTestClass()

    def test_readonly_lambda(self):
        class TestOwner:
            test_instance = Fixed(lambda _: CommonTestClass())

        owner = TestOwner()
        with pytest.raises(AttributeError, match="Setting `Fixed` parameter TestOwner.test_instance is forbidden!"):
            owner.test_instance = CommonTestClass()

    def test_function_to_eval(self):
        eval_str = ipylab.common.module_obj_to_import_string(test_last_updated_dict)
        obj = eval(eval_str, {"import_item": ipylab.common.import_item})  # noqa: S307
        assert obj is test_last_updated_dict
