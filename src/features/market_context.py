from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import pandas as pd
from src.market.candles import MultiTimeframeState
from src.indicators.trend import calculate_ema, calculate_rsi, calculate_atr, calculate_volume_sma
from src.features.structure import identify_swings, determine_trend, find_nearest_levels

class PositionState(BaseModel):
    has_position: bool = False
    side: Optional[str] = None
    entry_price: Optional[float] = None
    quantity: Optional[float] = None
    leverage: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    age_candles: Optional[int] = None # approximate

class TimeframeContext(BaseModel):
    timeframe: str
    trend: str
    current_price: float
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    rsi: Optional[float] = None
    atr: Optional[float] = None
    volume_sma: Optional[float] = None
    nearest_support: Optional[float] = None
    nearest_resistance: Optional[float] = None
    recent_closed_candles: List[Dict[str, Any]] = Field(default_factory=list)

class MarketContext(BaseModel):
    symbol: str
    position_state: PositionState
    tf_1h: TimeframeContext
    tf_15m: TimeframeContext
    tf_5m: TimeframeContext

class MarketContextBuilder:
    def __init__(self, llm_candle_context: int = 30):
        self.llm_candle_context = llm_candle_context

    def _build_tf_context(self, tf: str, df: pd.DataFrame, current_price: float) -> TimeframeContext:
        if len(df) < 50:
            # Not enough data for full context, return defaults
            return TimeframeContext(
                timeframe=tf,
                trend="UNKNOWN",
                current_price=current_price
            )

        df_calc = df.copy()

        # Calculate Indicators
        df_calc['ema_20'] = calculate_ema(df_calc['close'], 20)
        df_calc['ema_50'] = calculate_ema(df_calc['close'], 50)
        df_calc['rsi'] = calculate_rsi(df_calc['close'], 14)
        df_calc['atr'] = calculate_atr(df_calc, 14)
        df_calc['vol_sma'] = calculate_volume_sma(df_calc['volume'], 20)

        # Swings & Structure
        swings = identify_swings(df_calc, window=5)
        trend = determine_trend(swings)

        all_levels = swings["highs"] + swings["lows"]
        nearest = find_nearest_levels(current_price, all_levels)

        last_row = df_calc.iloc[-1]

        # Extract recent closed candles for LLM context
        # Convert index (timestamp) back to int for JSON serialization
        recent_df = df.iloc[-self.llm_candle_context:].copy()
        recent_df.reset_index(inplace=True)
        recent_df['timestamp'] = recent_df['timestamp'].astype(int) // 10**6 # if datetime64[ns]

        recent_candles = recent_df.to_dict('records')

        return TimeframeContext(
            timeframe=tf,
            trend=trend,
            current_price=current_price,
            ema_20=float(last_row['ema_20']) if not pd.isna(last_row['ema_20']) else None,
            ema_50=float(last_row['ema_50']) if not pd.isna(last_row['ema_50']) else None,
            rsi=float(last_row['rsi']) if not pd.isna(last_row['rsi']) else None,
            atr=float(last_row['atr']) if not pd.isna(last_row['atr']) else None,
            volume_sma=float(last_row['vol_sma']) if not pd.isna(last_row['vol_sma']) else None,
            nearest_support=nearest['support'],
            nearest_resistance=nearest['resistance'],
            recent_closed_candles=recent_candles
        )

    def build_context(self, state: MultiTimeframeState, position: Optional[Dict[str, Any]] = None) -> MarketContext:
        pos_state = PositionState()
        if position:
            pos_state = PositionState(
                has_position=True,
                side=position.get("side"),
                entry_price=position.get("entry_price"),
                quantity=position.get("quantity"),
                leverage=position.get("leverage"),
                unrealized_pnl=position.get("unrealized_pnl"),
                stop_loss=position.get("stop_loss"),
                take_profit=position.get("take_profit"),
                age_candles=None # Will be updated by execution engine if needed
            )

        current_price = state.mark_price

        ctx_1h = self._build_tf_context("1H", state.get_dataframe("1H"), current_price)
        ctx_15m = self._build_tf_context("15M", state.get_dataframe("15M"), current_price)
        ctx_5m = self._build_tf_context("5M", state.get_dataframe("5M"), current_price)

        return MarketContext(
            symbol=state.symbol,
            position_state=pos_state,
            tf_1h=ctx_1h,
            tf_15m=ctx_15m,
            tf_5m=ctx_5m
        )
