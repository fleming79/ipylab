from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import async_kernel
import async_kernel.interface
import ipylab
import ipylab.ipylab
import pytest
from async_kernel.typing import Channel

if TYPE_CHECKING:
    from async_kernel.caller import Caller
    from ipylab.jupyterfrontend import JupyterFrontEnd


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend):
    return anyio_backend


@pytest.fixture(scope="session")
async def kernel(anyio_backend):
    def send(msg, buffers, requires_reply):
        assert not requires_reply

    handlers = await async_kernel.interface.start_kernel_callable_interface(send=send, stopped=lambda: None)
    try:
        yield async_kernel.Kernel()
    finally:
        handlers["stop"]()


@pytest.fixture
async def caller(kernel: async_kernel.Kernel) -> Caller:
    return kernel.caller


@pytest.fixture
async def app(kernel: async_kernel.Kernel, mocker) -> JupyterFrontEnd:
    app = ipylab.JupyterFrontEnd()
    ipylab.ipylab.WAIT_READY = False
    app.set_trait("_vpath", "testing_vpath")
    mocker.patch.object(app, "wait_ready")

    job = {
        "socket_id": Channel.shell,
        "ident": [b"3e829a23-efc115ccfdfa9f2a9bb11e67"],
        "msg": {
            "header": {
                "msg_id": "3e829a23-efc115ccfdfa9f2a9bb11e67_1370907_0",
                "msg_type": "history_request",
                "username": "alan",
                "session": "456",
                "date": datetime.datetime(2025, 10, 20, 21, 1, 14, 896627, tzinfo=datetime.UTC),
                "version": "5.3",
            },
            "msg_id": "3e829a23-efc115ccfdfa9f2a9bb11e67_1370907_0",
            "msg_type": "history_request",
            "parent_header": {},
            "metadata": {},
            "content": {},
            "buffers": [],
        },
        "received_time": 275786.487449944,
    }
    async_kernel.utils._job_var.set(job)  # pyright: ignore[reportArgumentType]

    return app
