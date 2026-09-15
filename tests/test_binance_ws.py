import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch
from src.market.binance import BinanceMarketDataAdapter

@pytest.mark.asyncio
async def test_binance_ws_parsing():
    adapter = BinanceMarketDataAdapter()
    callback = AsyncMock()

    # Mock payload for combined markPriceUpdate
    payload_mark = json.dumps({
        "stream": "btcusdt@markPrice",
        "data": {
            "e": "markPriceUpdate",
            "E": 1562305380000,
            "s": "BTCUSDT",
            "p": "11794.15000000",
            "i": "11784.62659091",
            "P": "11784.25641265",
            "r": "0.00038167",
            "T": 1562306400000
        }
    })

    # Mock payload for combined 5m kline (forming)
    payload_kline_forming = json.dumps({
        "stream": "btcusdt@kline_5m",
        "data": {
            "e": "kline",
            "E": 123456789,
            "s": "BTCUSDT",
            "k": {
                "t": 123400000,
                "T": 123460000,
                "s": "BTCUSDT",
                "i": "5m",
                "f": 100,
                "L": 200,
                "o": "0.0010",
                "c": "0.0020",
                "h": "0.0025",
                "l": "0.0015",
                "v": "1000",
                "n": 100,
                "x": False,
                "q": "1.0000",
                "V": "500",
                "Q": "0.500",
                "B": "123456"
            }
        }
    })

    # Mock payload for combined 15m kline (closed)
    payload_kline_closed = json.dumps({
        "stream": "btcusdt@kline_15m",
        "data": {
            "e": "kline",
            "E": 123456789,
            "s": "BTCUSDT",
            "k": {
                "t": 123400000,
                "T": 123460000,
                "s": "BTCUSDT",
                "i": "15m",
                "f": 100,
                "L": 200,
                "o": "1.0010",
                "c": "1.0020",
                "h": "1.0025",
                "l": "1.0015",
                "v": "1000",
                "n": 100,
                "x": True,
                "q": "1.0000",
                "V": "500",
                "Q": "0.500",
                "B": "123456"
            }
        }
    })

    class MockWS:
        def __init__(self, messages):
            self.messages = messages
            self.index = 0

        async def recv(self):
            if self.index < len(self.messages):
                msg = self.messages[self.index]
                self.index += 1
                return msg
            else:
                # Cancel the connection loop after messages
                raise asyncio.CancelledError()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_ws_instance = MockWS([payload_mark, payload_kline_forming, payload_kline_closed])

    with patch('websockets.connect', return_value=mock_ws_instance):
        try:
            await adapter.connect_websocket(["BTCUSDT"], callback)
        except asyncio.CancelledError:
            pass

    # Assertions
    assert callback.call_count == 3

    call_mark = callback.call_args_list[0][0][0]
    assert call_mark["type"] == "mark_price"
    assert call_mark["symbol"] == "BTCUSDT"
    assert call_mark["price"] == 11794.15

    call_forming = callback.call_args_list[1][0][0]
    assert call_forming["type"] == "candle"
    assert call_forming["symbol"] == "BTCUSDT"
    assert call_forming["timeframe"] == "5M"
    assert call_forming["is_closed"] is False
    assert call_forming["close"] == 0.0020

    call_closed = callback.call_args_list[2][0][0]
    assert call_closed["type"] == "candle"
    assert call_closed["symbol"] == "BTCUSDT"
    assert call_closed["timeframe"] == "15M"
    assert call_closed["is_closed"] is True
    assert call_closed["open"] == 1.0010
