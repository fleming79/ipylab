# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import pytest
from ipywidgets import TypedTuple
from traitlets import HasTraits, Unicode

from ipylab.common import (
    Fixed,
    FixedCreate,
    FixedCreated,
    LastUpdatedDict,
    Transform,
    TransformDictAdvanced,
    TransformDictConnection,
    TransformDictFunction,
    trait_tuple_add,
)
from ipylab.connection import Connection


class CommonTestClass:
    def __init__(self, value):
        self.value = value


def test_trait_tuple_add():
    class TestHasTraits(HasTraits):
        test_tuple = TypedTuple(trait=Unicode(), default_value=())

    owner = TestHasTraits()
    trait_tuple_add(owner, "test_tuple", "value1")
    assert owner.test_tuple == ("value1",)
    trait_tuple_add(owner, "test_tuple", "value2")
    assert owner.test_tuple == ("value1", "value2")
    trait_tuple_add(owner, "test_tuple", "value1")  # Should not add duplicate
    assert owner.test_tuple == ("value1", "value2")


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


class TestTransformPayload:
    def test_transform_payload_advanced(self):
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
        result = Transform.transform_payload(transform, payload)
        assert isinstance(result, dict)
        assert "key1" in result
        assert "key2" in result

    def test_transform_payload_connection(self):
        transform: TransformDictConnection = {
            "transform": Transform.connection,
            "cid": "ipylab-Connection",
        }
        payload = {"cid": "ipylab-Connection"}
        result = Transform.transform_payload(transform, payload)
        assert isinstance(result, Connection)

    def test_transform_payload_auto(self):
        transform = Transform.auto
        payload = {"cid": "ipylab-Connection"}
        result = Transform.transform_payload(transform, payload)
        assert isinstance(result, Connection)

    def test_transform_payload_no_transform(self):
        transform = Transform.null
        payload = {"key": "value"}
        result = Transform.transform_payload(transform, payload)
        assert result == payload


class TestFixed:
    def test_readonly_basic(self):
        class TestOwner:
            test_instance = Fixed(CommonTestClass, 42)

        owner = TestOwner()
        instance = owner.test_instance
        assert isinstance(instance, CommonTestClass)
        assert instance.value == 42

    def test_readonly_dynamic(self):
        class TestOwner:
            value: int
            test_instance = Fixed(CommonTestClass, value=lambda obj: obj.value, dynamic=["value"])

        owner = TestOwner()
        owner.value = 100
        assert isinstance(owner.test_instance, CommonTestClass)
        assert owner.test_instance.value == 100

    def test_readonly_create_function(self):
        class TestOwner:
            test_instance = Fixed(CommonTestClass, create=lambda info: CommonTestClass(**info["kwgs"]), value=200)

        owner = TestOwner()
        instance = owner.test_instance
        assert isinstance(instance, CommonTestClass)
        assert instance.value == 200

    def test_readonly_create_method(self):
        class TestOwner:
            test_instance = Fixed(CommonTestClass, create="_create_callback", value=200)

            def _create_callback(self, info: FixedCreate):
                assert info["owner"] is self
                assert info["klass"] is CommonTestClass
                assert info["kwgs"] == {"value": 200}
                return CommonTestClass(*info["args"], **info["kwgs"])

        owner = TestOwner()
        instance = owner.test_instance
        assert isinstance(instance, CommonTestClass)
        assert instance.value == 200

    def test_readonly_created_callback_method(self):
        class TestOwner:
            test_instance = Fixed(CommonTestClass, created="instance_created", value=300)

            def instance_created(self, info: FixedCreated):
                assert isinstance(info["obj"], CommonTestClass)
                assert info["obj"].value == 300
                assert info["owner"] is self

        owner = TestOwner()
        assert isinstance(owner.test_instance, CommonTestClass)
        assert owner.test_instance.value == 300

    def test_readonly_forbidden_set(self):
        class TestOwner:
            test_instance = Fixed(CommonTestClass, 42)

        owner = TestOwner()
        with pytest.raises(AttributeError, match="Setting TestOwner.test_instance is forbidden!"):
            owner.test_instance = CommonTestClass(100)
