# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from async_kernel import Caller

if TYPE_CHECKING:
    import ipylab


def example_callable(a=None):
    return a


async def example_async_callable(c):
    return c


@pytest.mark.parametrize(
    ("kw", "result"),
    [
        (
            {"evaluate": "'simple evaluation'"},
            "simple evaluation",
        ),
        (
            {"evaluate": ["a='eval exec eval'", ("b", example_callable), "payload=b"]},  # payload is b
            "eval exec eval",
        ),
        (
            {
                "evaluate": [("b", example_callable), ("payload", "None"), "b"],  # payload is b
                "kwgs": {"a": "eval exec eval with variable"},
            },
            "eval exec eval with variable",
        ),
        (
            {
                "evaluate": ["a='simple callable'", ("b", example_callable), "b"],  # payload is b
                "namespace_id": "ns1",
            },
            "simple callable",
        ),
        (
            {
                "evaluate": example_callable,
                "namespace_id": "ns2",
                "kwgs": {"a": "ns2 variable"},
            },
            "ns2 variable",
        ),
        (
            {
                "evaluate": example_async_callable,
                "kwgs": {"c": "async callable"},
            },
            "async callable",
        ),
    ],
)
async def test_app_evaluate(app: ipylab.App, kw: dict[str, Any], result, mocker):
    "Tests for app.evaluate"

    ready = mocker.patch.object(app, "ready")
    send = mocker.patch.object(app, "send")

    Caller().call_soon(app.evaluate, **kw, vpath="irrelevant")
    await anyio.sleep(0.01)
    assert ready.call_count == 2
    assert send.call_count == 1

    # Simulate relaying the message from the frontend to a kernel (this kernel).
    be_msg = json.loads(send.call_args[0][0]["ipylab"])
    assert list(be_msg) == ["ipylab_PY", "operation", "kwgs", "transform"]
    result_ = await app._evaluate(be_msg["kwgs"], [])
    # Check expected result
    assert result_["payload"] == result


loops = set()


@pytest.mark.parametrize("n", [1, 2])
async def test_ready(n, app: ipylab.App):
    "Paramatised tests must be run consecutively."
    # Normally not an issue, but when testing, it is possible for asyncio to
    # use different loops. Running this test consecutively should use separate
    # event loops.
    loops.add(asyncio.get_running_loop())
    assert len(loops) == n, "A new event loop should be provided per test."
    with contextlib.suppress(TimeoutError):
        with anyio.fail_after(1):
            await app.ready()
