from unittest.mock import AsyncMock, MagicMock

from ipylab.ipylab import Ipylab
from ipylab.jupyterfrontend import App


class TestOnReady:
    async def test_on_ready_add_and_remove(self):
        obj = Ipylab()
        callback = MagicMock()

        # Add the callback
        obj.on_ready(callback)
        assert callback in obj._on_ready_callbacks

        # Simulate the ready event
        obj.set_trait("_ready", True)
        callback.assert_called()

        callback.reset_mock()
        obj.set_trait("_ready", False)
        obj.set_trait("_ready", True)
        callback.assert_called()

        # Reset the mock and remove the callback
        callback.reset_mock()
        obj.on_ready(callback, remove=True)
        assert callback not in obj._on_ready_callbacks

        # Simulate the ready event again, callback should not be called
        obj.set_trait("_ready", False)
        obj.set_trait("_ready", True)
        callback.assert_not_called()

        obj.close()

    async def test_on_ready_async(self, app: App):
        obj = Ipylab()
        callback = AsyncMock()

        # Add the callback
        obj.on_ready(callback)
        assert callback in obj._on_ready_callbacks

        # Simulate the ready event
        obj.set_trait("_ready", True)
        callback.assert_called()
        assert callback.await_count == 1  # With eager task factory this should already be called.
        assert callback.call_args[0][0] is obj
        obj.close()
