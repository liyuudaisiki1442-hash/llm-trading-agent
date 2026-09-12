import pandas as pd
from typing import Dict, Any, List

def identify_swings(df: pd.DataFrame, window: int = 5) -> Dict[str, List[float]]:
    """
    Identifies swing highs and lows in a dataframe.
    Window is the number of candles before and after that must be lower/higher.
    Returns a dict with 'highs' and 'lows'.
    """
    if len(df) < window * 2 + 1:
        return {"highs": [], "lows": []}

    highs = []
    lows = []

    # We don't identify swings on the very edge
    for i in range(window, len(df) - window):
        is_high = True
        is_low = True

        current_high = df.iloc[i]['high']
        current_low = df.iloc[i]['low']

        for j in range(1, window + 1):
            if df.iloc[i-j]['high'] > current_high or df.iloc[i+j]['high'] > current_high:
                is_high = False
            if df.iloc[i-j]['low'] < current_low or df.iloc[i+j]['low'] < current_low:
                is_low = False

        if is_high:
            highs.append(float(current_high))
        if is_low:
            lows.append(float(current_low))

    return {"highs": highs, "lows": lows}

def determine_trend(swings: Dict[str, List[float]]) -> str:
    """
    Basic structure:
    HH + HL = UPTREND
    LH + LL = DOWNTREND
    Otherwise = RANGING
    """
    highs = swings["highs"]
    lows = swings["lows"]

    if len(highs) < 2 or len(lows) < 2:
        return "RANGING"

    last_two_highs = highs[-2:]
    last_two_lows = lows[-2:]

    if last_two_highs[1] > last_two_highs[0] and last_two_lows[1] > last_two_lows[0]:
        return "UPTREND"
    elif last_two_highs[1] < last_two_highs[0] and last_two_lows[1] < last_two_lows[0]:
        return "DOWNTREND"
    else:
        return "RANGING"

def find_nearest_levels(current_price: float, levels: List[float]) -> Dict[str, float]:
    above = [l for l in levels if l > current_price]
    below = [l for l in levels if l < current_price]

    nearest_resistance = min(above) if above else None
    nearest_support = max(below) if below else None

    return {
        "resistance": nearest_resistance,
        "support": nearest_support
    }
