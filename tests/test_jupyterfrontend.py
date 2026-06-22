# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from async_kernel.compat.json import pack_json_str
from ipylab.common import json_default

if TYPE_CHECKING:
    import ipylab


def example_callable(a):
    return a


async def example_async_callable(c):
    return c


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"evaluate": "'🐑'"}, "🐑"),
        ({"evaluate": ["a='🌈'", ("b", example_callable), "b"]}, "🌈"),
        ({"evaluate": [("b", example_callable), "b"], "kwgs": {"a": "⛵"}}, "⛵"),
        ({"evaluate": ["a='👽'", ("b", example_callable), "b"]}, "👽"),
        ({"evaluate": example_callable, "kwgs": {"a": "👿"}}, "👿"),
        ({"evaluate": example_async_callable, "kwgs": {"c": "🔨"}}, "🔨"),
    ],
)
async def test_app_evaluate(app: ipylab.JupyterFrontEnd, kw: dict[str, Any], expected, mocker):
    "Tests for app.evaluate"
    kw = json.loads(pack_json_str(kw, default=json_default))
    result = await app.evaluate(**kw, vpath=app.vpath)
    assert result["payload"] == expected
