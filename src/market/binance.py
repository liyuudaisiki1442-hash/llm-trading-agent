import httpx
import websockets
import json
import asyncio
from typing import List, Dict, Any, Optional
from src.market.exchange import ExchangeMarketData, ExchangeExecution
from src.monitoring.logging import logger

class BinanceMarketDataAdapter(ExchangeMarketData):
    def __init__(self, base_url: str = "https://fapi.binance.com", ws_url: str = "wss://fstream.binance.com/stream?streams="):
        self.base_url = base_url
        self.ws_url = ws_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        await self.client.aclose()

    def _map_timeframe(self, tf: str) -> str:
        mapping = {"5M": "5m", "15M": "15m", "1H": "1h"}
        return mapping.get(tf, "5m")

    async def fetch_historical_candles(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        interval = self._map_timeframe(timeframe)
        url = f"{self.base_url}/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }

        for attempt in range(3):
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                candles = []
                for kline in data:
                    candles.append({
                        "timestamp": int(kline[0]),
                        "open": float(kline[1]),
                        "high": float(kline[2]),
                        "low": float(kline[3]),
                        "close": float(kline[4]),
                        "volume": float(kline[5]),
                        "is_closed": True # We assume fetched historical candles are closed except potentially the last one.
                    })

                # Binance returns the currently forming candle as the last one.
                # To be safe and strict, we remove it to only return fully closed candles.
                if len(candles) > 0:
                    candles.pop()

                return candles
            except Exception as e:
                logger.error(f"Error fetching historical candles for {symbol} {timeframe}: {e}. Attempt {attempt+1}")
                await asyncio.sleep(2 ** attempt)

        raise Exception(f"Failed to fetch historical candles for {symbol} {timeframe}")

    async def connect_websocket(self, symbols: List[str], callback: callable):
        streams = []
        for sym in symbols:
            s = sym.lower()
            streams.append(f"{s}@kline_5m")
            streams.append(f"{s}@kline_15m")
            streams.append(f"{s}@kline_1h")
            streams.append(f"{s}@markPrice")

        stream_name = "/".join(streams)
        url = f"{self.ws_url}{stream_name}"

        while True:
            try:
                logger.info(f"Connecting to Binance WS: {url}")
                async with websockets.connect(url) as ws:
                    logger.info("Binance WS connected")
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)

                        # Handle combined streams wrapper
                        if "stream" in data and "data" in data:
                            payload = data["data"]
                        else:
                            payload = data

                        if "e" in payload:
                            event_type = payload["e"]
                            if event_type == "kline":
                                symbol = payload["s"]
                                kline = payload["k"]
                                interval = kline["i"]
                                tf = "5M" if interval == "5m" else "15M" if interval == "15m" else "1H" if interval == "1h" else None
                                if not tf:
                                    continue

                                candle = {
                                    "type": "candle",
                                    "symbol": symbol,
                                    "timeframe": tf,
                                    "timestamp": kline["t"],
                                    "open": float(kline["o"]),
                                    "high": float(kline["h"]),
                                    "low": float(kline["l"]),
                                    "close": float(kline["c"]),
                                    "volume": float(kline["v"]),
                                    "is_closed": kline["x"]
                                }
                                await callback(candle)
                            elif event_type == "markPriceUpdate":
                                symbol = payload["s"]
                                update = {
                                    "type": "mark_price",
                                    "symbol": symbol,
                                    "price": float(payload["p"]),
                                    "timestamp": payload["E"]
                                }
                                await callback(update)
            except websockets.exceptions.ConnectionClosedError as e:
                logger.warning(f"Binance WS connection closed: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Binance WS error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
