# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any

import pytest

import ipylab


def example_callable(a=None):
    return a


async def example_async_callable(c, *, return_task=False):
    if return_task:
        import asyncio

        async def f():
            return "return task"

        return asyncio.create_task(f())
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
        (
            {
                "evaluate": example_async_callable,
                "kwgs": {"c": 123, "return_task": True},
            },
            "return task",
        ),
    ],
)
async def test_app_evaluate(kw: dict[str, Any], result, mocker):
    "Tests for app.evaluate"
    import asyncio

    app = ipylab.app
    ready = mocker.patch.object(app, "ready")
    send = mocker.patch.object(app, "send")

    task1 = app.evaluate(**kw, vpath="irrelevant")
    await asyncio.sleep(0)
    assert ready.call_count == 1
    assert send.call_count == 1

    # Simulate relaying the message from the frontend to a kernel (this kernel).
    be_msg = json.loads(send.call_args[0][0]["ipylab"])
    data = {
        "ipylab_FE": str(uuid.uuid4()),
        "operation": be_msg["operation"],
        "payload": be_msg["kwgs"],
    }
    fe_msg = {"ipylab": json.dumps(data)}

    # Simulate the message arriving in kernel and being processed
    task2 = app._on_custom_msg(None, fe_msg, [])
    assert isinstance(task2, asyncio.Task)
    async with asyncio.timeout(1):
        await task2
    assert send.call_count == 2
    be_msg2 = json.loads(send.call_args[0][0]["ipylab"])
    assert be_msg2["ipylab_FE"] == data["ipylab_FE"]

    # Check expected result
    assert be_msg2["payload"] == result

    # Don't attempt to relay the result back
    task1.cancel()


loops = set()


@pytest.mark.parametrize("n", [1, 2])
async def test_ready(n):
    "Paramatised tests must be run consecutively."
    # Normally not an issue, but when testing, it is possible for asyncio to
    # use different loops. Running this test consecutively should use separate
    # event loops.

    loops.add(asyncio.get_running_loop())
    assert len(loops) == n, "A new event loop should be provided per test."
    with contextlib.suppress(asyncio.TimeoutError):
        async with asyncio.timeout(1):
            await ipylab.app.ready()
