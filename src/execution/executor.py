import asyncio
from typing import Dict, Any, List, Optional
from src.config.settings import settings
from src.monitoring.logging import logger

class LocalPaperExecutor:
    def __init__(self, initial_balance: float = settings.PAPER_INITIAL_BALANCE):
        self.balance = initial_balance
        self.available_balance = initial_balance

        # Position state tracking
        self.position: Optional[Dict[str, Any]] = None
        self.realized_pnl = 0.0
        self.trade_history: List[Dict[str, Any]] = []

        self.fee_rate = 0.0004 # 0.04% taker fee approximation

    def get_position(self) -> Optional[Dict[str, Any]]:
        return self.position

    def execute_params(self, params: Dict[str, Any]):
        """
        Executes a new trade based on validated parameters from RiskManager.
        """
        symbol = params["symbol"]
        side = params["side"]
        quantity = params["quantity"]
        entry_price = params["entry_price"]
        stop_loss = params["stop_loss"]
        take_profit = params["take_profit"]
        leverage = params["leverage"]

        position_value = quantity * entry_price
        fee = position_value * self.fee_rate
        margin_required = position_value / leverage if leverage > 0 else position_value

        if margin_required + fee > self.available_balance:
            logger.error(f"Insufficient paper balance to execute {side} {quantity} {symbol}.")
            return

        self.balance -= fee
        self.available_balance -= (margin_required + fee)

        self.position = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "leverage": leverage,
            "margin": margin_required,
            "unrealized_pnl": 0.0,
            "candles_held": 0
        }

        logger.info(f"PAPER EXECUTED: {side} {quantity} {symbol} @ {entry_price} (SL: {stop_loss}, TP: {take_profit})")

    def update_price(self, current_price: float):
        """
        Deterministic safety layer triggered on every price update (tick).
        Checks Stop Loss, Take Profit, and Liquidation.
        """
        if not self.position:
            return

        pos = self.position
        side = pos["side"]
        entry = pos["entry_price"]
        quantity = pos["quantity"]
        sl = pos["stop_loss"]
        tp = pos["take_profit"]
        margin = pos["margin"]

        # Calculate PnL
        if side == "LONG":
            pnl = (current_price - entry) * quantity
        else:
            pnl = (entry - current_price) * quantity

        self.position["unrealized_pnl"] = pnl

        # Check hard stops
        should_close = False
        close_reason = ""

        if side == "LONG":
            if current_price <= sl:
                should_close = True
                close_reason = "STOP_LOSS"
            elif current_price >= tp:
                should_close = True
                close_reason = "TAKE_PROFIT"
        else: # SHORT
            if current_price >= sl:
                should_close = True
                close_reason = "STOP_LOSS"
            elif current_price <= tp:
                should_close = True
                close_reason = "TAKE_PROFIT"

        # Simple liquidation approximation (if loss exceeds margin)
        # Disclaimer: This is a rough estimation. Binance cross/isolated margin mechanics are complex.
        if pnl < 0 and abs(pnl) >= (margin * 0.9): # 90% maintenance margin approximation
            should_close = True
            close_reason = "LIQUIDATION"

        if should_close:
            self.close_position(current_price, close_reason)

    def close_position(self, current_price: float, reason: str = "MANUAL_CLOSE"):
        """
        Closes the active position.
        """
        if not self.position:
            return

        pos = self.position
        side = pos["side"]
        entry = pos["entry_price"]
        quantity = pos["quantity"]

        if side == "LONG":
            pnl = (current_price - entry) * quantity
        else:
            pnl = (entry - current_price) * quantity

        position_value = quantity * current_price
        fee = position_value * self.fee_rate

        net_pnl = pnl - fee
        self.balance += net_pnl
        self.realized_pnl += net_pnl

        # Release margin back to available
        self.available_balance = self.balance

        logger.info(f"PAPER CLOSED ({reason}): {side} {quantity} @ {current_price}. PnL: {net_pnl:.2f}, New Balance: {self.balance:.2f}")

        self.trade_history.append({
            "symbol": pos["symbol"],
            "side": side,
            "entry_price": entry,
            "exit_price": current_price,
            "quantity": quantity,
            "pnl": net_pnl,
            "reason": reason
        })

        self.position = None

    def increment_candle_age(self):
        if self.position:
            self.position["candles_held"] += 1
