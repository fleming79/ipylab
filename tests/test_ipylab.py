from unittest.mock import AsyncMock, MagicMock

import anyio
from ipylab.ipylab import Ipylab
from ipylab.jupyterfrontend import App


class TestOnReady:
    async def test_on_ready_add_and_remove(self, caller):
        obj = Ipylab()
        callback = MagicMock()

        # Add the callback
        obj.on_ready(callback)
        assert callback in obj._on_ready_callbacks

        # Simulate the 'ready' message
        obj._set_ready()
        assert obj._ready
        await anyio.sleep(0.1)
        callback.assert_called()

        callback.reset_mock()
        obj._set_ready()
        await anyio.sleep(0.1)
        callback.assert_called()

        # Reset the mock and remove the callback
        callback.reset_mock()
        obj.on_ready(callback, remove=True)
        assert callback not in obj._on_ready_callbacks

        # Simulate the ready event again, callback should not be called
        obj.set_trait("_ready", False)
        obj.set_trait("_ready", True)
        await anyio.sleep(0.1)
        callback.assert_not_called()

        obj.close()

    async def test_on_ready_async(self, app: App):
        obj = Ipylab()
        callback = AsyncMock()

        # Add the callback
        obj.on_ready(callback)
        assert callback in obj._on_ready_callbacks

        # Simulate the ready event
        obj._set_ready()
        await anyio.sleep(0.1)
        callback.assert_called()
        await anyio.sleep(0.1)
        assert callback.await_count == 1
        obj.close()
