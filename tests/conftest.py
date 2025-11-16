import datetime
import threading

import async_kernel
import ipylab
import ipylab.ipylab
import pytest
from async_kernel import Caller
from async_kernel.kernel import RunMode, SocketID


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend):
    return anyio_backend


@pytest.fixture
async def caller(anyio_backend):
    async with Caller(thread=threading.current_thread()) as caller:
        yield caller


@pytest.fixture
async def app(caller, mocker):
    app = ipylab.JupyterFrontEnd()
    ipylab.ipylab.WAIT_READY = False
    mocker.patch.object(app, "ready")
    page_id = "123"
    client_id = "456"
    ipylab.ipylab._page_id_var.set(page_id)
    ipylab.ipylab._client_id_to_page[client_id] = page_id

    def get_kernel_client_id():
        return client_id

    mocker.patch.object(app, "get_kernel_client_id", get_kernel_client_id)

    job = {
        "socket_id": SocketID.shell,
        "socket": None,
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
        "run_mode": RunMode.thread,
    }
    async_kernel.utils._job_var.set(job)

    return app
