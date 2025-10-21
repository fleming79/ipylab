import datetime

import async_kernel
import ipylab
import ipylab.ipylab
import pytest
from async_kernel import Caller
from async_kernel.kernel import AsyncEvent, RunMode, SocketID


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend):
    return anyio_backend


@pytest.fixture
async def caller(anyio_backend):
    async with Caller(create=True) as caller:
        yield caller


@pytest.fixture
async def app(caller, mocker):
    app = ipylab.App()
    mocker.patch.object(app, "ready")
    return app


@pytest.fixture
async def mock_connection(app, mocker):
    page_id = "123"
    ipylab.ipylab._page_id_var.set(page_id)
    ipylab.ipylab._session_to_page["456"] = page_id

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
    mocker.patch.object(AsyncEvent, "wait")
