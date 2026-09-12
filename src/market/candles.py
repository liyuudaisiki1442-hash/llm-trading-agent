from typing import List, Dict, Any, Optional
import pandas as pd

class MultiTimeframeState:
    def __init__(self, symbol: str, limit: int = 500):
        self.symbol = symbol
        self.limit = limit

        # Storing history as list of dicts for easy appending, convert to DataFrame on demand for indicators
        self.history_1h: List[Dict[str, Any]] = []
        self.history_15m: List[Dict[str, Any]] = []
        self.history_5m: List[Dict[str, Any]] = []

        # Currently forming candles
        self.current_1h: Optional[Dict[str, Any]] = None
        self.current_15m: Optional[Dict[str, Any]] = None
        self.current_5m: Optional[Dict[str, Any]] = None

        # Last known mark price
        self.mark_price: float = 0.0

    def initialize_history(self, tf: str, candles: List[Dict[str, Any]]):
        if tf == "1H":
            self.history_1h = candles[-self.limit:]
        elif tf == "15M":
            self.history_15m = candles[-self.limit:]
        elif tf == "5M":
            self.history_5m = candles[-self.limit:]

    def update_candle(self, tf: str, candle: Dict[str, Any]):
        """
        Updates the state with a new candle update.
        If the candle is closed, appends it to the history and clears the current forming candle.
        If it's forming, updates the current forming candle.
        """
        if candle["is_closed"]:
            # Append to history and enforce limit
            if tf == "1H":
                self.history_1h.append(candle)
                self.history_1h = self.history_1h[-self.limit:]
                self.current_1h = None
            elif tf == "15M":
                self.history_15m.append(candle)
                self.history_15m = self.history_15m[-self.limit:]
                self.current_15m = None
            elif tf == "5M":
                self.history_5m.append(candle)
                self.history_5m = self.history_5m[-self.limit:]
                self.current_5m = None
        else:
            # Update forming candle
            if tf == "1H":
                self.current_1h = candle
            elif tf == "15M":
                self.current_15m = candle
            elif tf == "5M":
                self.current_5m = candle

    def update_mark_price(self, price: float):
        self.mark_price = price

    def get_dataframe(self, tf: str) -> pd.DataFrame:
        """
        Returns a pandas DataFrame of the CLOSED candles for the given timeframe.
        """
        history = []
        if tf == "1H":
            history = self.history_1h
        elif tf == "15M":
            history = self.history_15m
        elif tf == "5M":
            history = self.history_5m

        if not history:
            return pd.DataFrame()

        df = pd.DataFrame(history)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
