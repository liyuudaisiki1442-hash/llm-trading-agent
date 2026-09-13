from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class ExchangeMarketData(ABC):
    @abstractmethod
    async def fetch_historical_candles(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        """
        Fetch historical closed candles.
        Returns a list of dictionaries with keys:
        timestamp, open, high, low, close, volume, is_closed
        """
        pass

    @abstractmethod
    async def connect_websocket(self, symbols: List[str], callback: callable):
        """
        Connects to the websocket for real-time tick and candle updates.
        Callback should accept a dictionary with the update data.
        """
        pass

class ExchangeExecution(ABC):
    @abstractmethod
    async def get_balance(self) -> Dict[str, Any]:
        """Get account balances."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current open positions."""
        pass

    @abstractmethod
    async def create_order(self, symbol: str, side: str, quantity: float, order_type: str, price: Optional[float] = None) -> Dict[str, Any]:
        """Create a new order."""
        pass
