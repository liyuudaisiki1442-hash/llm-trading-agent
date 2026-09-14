import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.market.binance import BinanceMarketDataAdapter

@pytest.mark.asyncio
async def test_binance_ws_url_and_1h():
    adapter = BinanceMarketDataAdapter()
    callback = AsyncMock()

    class MockWS:
        def __init__(self):
            pass
        async def recv(self):
            # Send one 1h payload then cancel
            import json
            yield json.dumps({
                "stream": "btcusdt@kline_1h",
                "data": {
                    "e": "kline",
                    "E": 12345,
                    "s": "BTCUSDT",
                    "k": {
                        "t": 1234, "T": 1235, "s": "BTCUSDT", "i": "1h", "f": 100, "L": 200,
                        "o": "10", "c": "15", "h": "20", "l": "5", "v": "1000",
                        "n": 100, "x": True, "q": "1.0", "V": "500", "Q": "0.5", "B": "1"
                    }
                }
            })
            raise asyncio.CancelledError()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    async def mock_recv():
        import json
        payload = json.dumps({
            "stream": "btcusdt@kline_1h",
            "data": {
                "e": "kline",
                "E": 12345,
                "s": "BTCUSDT",
                "k": {
                    "t": 1234, "T": 1235, "s": "BTCUSDT", "i": "1h", "f": 100, "L": 200,
                    "o": "10", "c": "15", "h": "20", "l": "5", "v": "1000",
                    "n": 100, "x": True, "q": "1.0", "V": "500", "Q": "0.5", "B": "1"
                }
            }
        })
        # Hack to return payload once then raise CancelledError
        if not hasattr(mock_recv, "called"):
            mock_recv.called = True
            return payload
        raise asyncio.CancelledError()

    mock_ws = AsyncMock()
    mock_ws.recv = mock_recv
    mock_ws.__aenter__.return_value = mock_ws

    with patch('websockets.connect', return_value=mock_ws) as mock_connect:
        try:
            await adapter.connect_websocket(["BTCUSDT"], callback)
        except asyncio.CancelledError:
            pass

    # Verify connection URL is the current official one, not old /ws
    mock_connect.assert_called_once()
    actual_url = mock_connect.call_args[0][0]
    assert "wss://fstream.binance.com/market/stream?streams=" in actual_url
    assert "/ws" not in actual_url # Old path should not exist

    # Verify 1h mapped correctly
    assert callback.call_count == 1
    event = callback.call_args_list[0][0][0]
    assert event["timeframe"] == "1H"
    assert event["is_closed"] is True
    assert event["close"] == 15.0
