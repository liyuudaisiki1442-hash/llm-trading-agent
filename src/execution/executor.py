import asyncio
from typing import Dict, Any, List, Optional
from src.config.settings import settings
from src.monitoring.logging import logger

from src.storage.database import SessionLocal
from src.storage.models import Trade, Position, AccountSnapshot, ActiveTradePlan
from datetime import datetime

class LocalPaperExecutor:
    def __init__(self, initial_balance: float = settings.PAPER_INITIAL_BALANCE):
        self.balance = initial_balance
        self.available_balance = initial_balance

        # Pending setup state
        self.pending_setup: Optional[Dict[str, Any]] = None
        self.setup_expiry_candles = 3

        # Position state tracking
        self.position: Optional[Dict[str, Any]] = None
        self.realized_pnl = 0.0
        self.trade_history: List[Dict[str, Any]] = []

        self.fee_rate = 0.0004 # 0.04% taker fee approximation
        self.active_trade_plan: Optional[Dict[str, Any]] = None
        self._load_state()

    def _load_state(self):
        db = SessionLocal()
        try:
            # Initialize or retrieve today's snapshot
            today = datetime.utcnow().date()
            today_dt = datetime(today.year, today.month, today.day)

            # Reconstruct balance from realized PnL
            # A more robust approach would be to track equity permanently, but for v1 paper trading
            # we sum up all closed trades to find the current balance.
            trades = db.query(Trade).filter(Trade.status == "CLOSED", Trade.realized_pnl != None).all()
            total_pnl = sum(t.realized_pnl for t in trades)
            self.realized_pnl = total_pnl

            self.balance = settings.PAPER_INITIAL_BALANCE + total_pnl
            self.available_balance = self.balance

            snapshot = db.query(AccountSnapshot).filter(AccountSnapshot.date == today_dt).first()
            if not snapshot:
                snapshot = AccountSnapshot(date=today_dt, equity=self.balance)
                db.add(snapshot)
                db.commit()

            # Restore active position if exists
            db_pos = db.query(Position).first()
            if db_pos:
                margin_required = (db_pos.quantity * db_pos.entry_price) / db_pos.leverage
                # Reconstruct initial fee since we didn't save it explicitly
                fee = (db_pos.quantity * db_pos.entry_price) * self.fee_rate
                self.balance -= fee
                self.available_balance = self.balance - margin_required

                self.position = {
                    "symbol": db_pos.symbol,
                    "side": db_pos.side,
                    "quantity": db_pos.quantity,
                    "entry_price": db_pos.entry_price,
                    "stop_loss": db_pos.stop_loss,
                    "take_profit": db_pos.take_profit,
                    "leverage": db_pos.leverage,
                    "margin": margin_required,
                    "unrealized_pnl": db_pos.unrealized_pnl,
                    "candles_held": 0, # approximation on restart
                    "db_id": db_pos.id
                }

                plan = db.query(ActiveTradePlan).filter(ActiveTradePlan.symbol == db_pos.symbol).first()
                if plan:
                    self.active_trade_plan = {
                        "side": plan.side,
                        "setup_type": plan.setup_type,
                        "entry_reason": plan.entry_reason,
                        "entry_zone_low": plan.entry_zone_low,
                        "entry_zone_high": plan.entry_zone_high,
                        "invalidation_price": plan.invalidation_price,
                        "original_stop_loss": plan.original_stop_loss,
                        "original_take_profit": plan.original_take_profit,
                        "original_first_obstacle": plan.original_first_obstacle,
                        "market_regime": plan.market_regime,
                        "created_at": plan.created_at.isoformat()
                    }
        except Exception as e:
            logger.error(f"Error loading state: {e}")
        finally:
            db.close()

    def get_position(self) -> Optional[Dict[str, Any]]:
        return self.position

    def execute_params(self, params: Dict[str, Any]):
        """
        Registers a pending setup based on validated parameters from RiskManager.
        Will only execute if price hits entry_zone.
        """
        self.pending_setup = params
        self.pending_setup = params.copy()
        self.pending_setup["candles_waited"] = 0
        logger.info(f"Registered pending setup for {params['side']} in zone {params['entry_zone']}")

    def _open_position(self, current_price: float):
        if not self.pending_setup:
            return

        params = self.pending_setup
        symbol = params["symbol"]
        side = params["side"]
        quantity = params["quantity"]

        # We enter at the current market price since it's within the zone
        entry_price = current_price

        stop_loss = params["stop_loss"]
        take_profit = params["take_profit"]
        leverage = params["leverage"]

        position_value = quantity * entry_price
        fee = position_value * self.fee_rate

        # We must re-verify if margin + fee fits within available balance at this actual entry price
        margin_required = position_value / leverage if leverage > 0 else position_value

        if margin_required + fee > self.available_balance:
            logger.error(f"Insufficient paper balance to execute {side} {quantity} {symbol} at {entry_price}. Margin required: {margin_required}, Fee: {fee}, Available: {self.available_balance}")
            self.pending_setup = None
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
            "unrealized_pnl": -fee,
            "candles_held": 0
        }

        db = SessionLocal()
        try:
            db_trade = Trade(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                quantity=quantity,
                leverage=leverage,
                status="OPEN"
            )
            db.add(db_trade)
            db.commit()

            db_pos = Position(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                quantity=quantity,
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                unrealized_pnl=-fee
            )
            db.add(db_pos)
            db.commit()

            # Persist Active Trade Plan exactly when position is filled
            db_plan = ActiveTradePlan(
                symbol=symbol,
                side=side,
                setup_type=params.get("setup_type"),
                entry_reason=params.get("entry_reason"),
                entry_zone_low=params.get("entry_zone", {}).get("low"),
                entry_zone_high=params.get("entry_zone", {}).get("high"),
                invalidation_price=params.get("invalidation_price"),
                original_stop_loss=stop_loss,
                original_take_profit=take_profit,
                original_first_obstacle=params.get("first_obstacle"),
                market_regime=params.get("market_regime")
            )
            db.add(db_plan)
            db.commit()

            self.position["db_id"] = db_pos.id
            self.position["trade_id"] = db_trade.id
            self.active_trade_plan = {
                "side": side,
                "setup_type": db_plan.setup_type,
                "entry_reason": db_plan.entry_reason,
                "entry_zone_low": db_plan.entry_zone_low,
                "entry_zone_high": db_plan.entry_zone_high,
                "invalidation_price": db_plan.invalidation_price,
                "original_stop_loss": db_plan.original_stop_loss,
                "original_take_profit": db_plan.original_take_profit,
                "original_first_obstacle": db_plan.original_first_obstacle,
                "market_regime": db_plan.market_regime,
                "created_at": db_plan.created_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to persist new position: {e}")
        finally:
            db.close()

        self.pending_setup = None
        logger.info(f"PAPER EXECUTED: {side} {quantity} {symbol} @ {entry_price} (SL: {stop_loss}, TP: {take_profit})")

    def update_stop_loss(self, new_stop: float, current_price: float):
        if not self.position:
            return

        pos = self.position
        side = pos["side"]
        current_stop = pos["stop_loss"]
        symbol = pos["symbol"]

        if side == "LONG":
            if new_stop <= current_stop:
                logger.info(f"Rejected stop update: {new_stop} is not tighter than current LONG stop {current_stop}.")
                return
            if new_stop >= current_price:
                logger.info(f"Rejected stop update: {new_stop} must be below current price {current_price} for LONG.")
                return
        elif side == "SHORT":
            if new_stop >= current_stop:
                logger.info(f"Rejected stop update: {new_stop} is not tighter than current SHORT stop {current_stop}.")
                return
            if new_stop <= current_price:
                logger.info(f"Rejected stop update: {new_stop} must be above current price {current_price} for SHORT.")
                return
        else:
            logger.warning(f"Rejected stop update: Unknown position side '{side}'")
            return

        db = SessionLocal()
        try:
            db_pos = db.query(Position).filter(Position.id == pos["db_id"]).first()
            if not db_pos:
                logger.error(f"Rejected stop update: DB Position row {pos['db_id']} not found.")
                db.rollback()
                return

            db_pos.stop_loss = new_stop
            db.commit()

            # Accepted and persisted successfully
            self.position["stop_loss"] = new_stop
            logger.info(f"PAPER STOP UPDATED: {side} {symbol} {current_stop} -> {new_stop}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist stop loss update: {e}. In-memory stop unchanged.")
        finally:
            db.close()

    def _check_and_rollover_daily_snapshot(self):
        """Check if UTC day changed and insert new snapshot if necessary."""
        today = datetime.utcnow().date()

        # In-memory cache to prevent DB hit on every tick
        if getattr(self, "_last_snapshot_date", None) == today:
            return

        db = SessionLocal()
        try:
            today_dt = datetime(today.year, today.month, today.day)
            snapshot = db.query(AccountSnapshot).filter(AccountSnapshot.date == today_dt).first()
            if not snapshot:
                snapshot = AccountSnapshot(date=today_dt, equity=self.balance)
                db.add(snapshot)
                db.commit()
                logger.info(f"Created new daily account snapshot for {today}: {self.balance:.2f}")

            self._last_snapshot_date = today
        except Exception as e:
            logger.error(f"Failed to check/create daily account snapshot: {e}")
        finally:
            db.close()

    def update_price(self, current_price: float):
        """
        Deterministic safety layer triggered on every price update (tick).
        Checks Entry Zones, Stop Loss, and Take Profit.
        """
        self._check_and_rollover_daily_snapshot()
        if self.pending_setup and not self.position:
            zone = self.pending_setup["entry_zone"]
            if zone["low"] <= current_price <= zone["high"]:
                self._open_position(current_price)

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

        # Also factor in the initial entry fee
        entry_fee = (entry * quantity) * self.fee_rate
        self.position["unrealized_pnl"] = pnl - entry_fee

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

        # Removed inaccurate liquidation approximation as requested.

        if should_close:
            self.close_position(current_price, close_reason)

        # Persist unrealized PnL occasionally (here we just keep memory up to date)

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

        # entry_fee was already deducted from balance when the position opened
        # Now we deduct exit fee from the raw PnL
        # However, to maintain exact ledger accuracy on restarts, we need to report
        # the FULL net trade PnL (pnl - entry_fee - exit_fee) into DB `realized_pnl`
        # so that summing realized_pnl during restart exactly reflects total equity changes.
        entry_fee = (entry * quantity) * self.fee_rate
        exit_fee = fee

        # The true net PnL of this entire trade lifecycle
        full_net_pnl = pnl - entry_fee - exit_fee

        # Balance only needs raw pnl - exit_fee added back (since entry_fee was already deducted)
        self.balance += (pnl - exit_fee)
        self.available_balance = self.balance

        # But we record the full_net_pnl so that `balance = PAPER_INITIAL_BALANCE + sum(realized_pnl)` works properly on restarts
        self.realized_pnl += full_net_pnl
        total_trade_fees = entry_fee + exit_fee

        logger.info(f"PAPER CLOSED ({reason}): {side} {quantity} @ {current_price}. Net PnL: {full_net_pnl:.2f}, New Balance: {self.balance:.2f}")

        self.trade_history.append({
            "symbol": pos["symbol"],
            "side": side,
            "entry_price": entry,
            "exit_price": current_price,
            "quantity": quantity,
            "pnl": full_net_pnl,
            "reason": reason
        })

        db = SessionLocal()
        try:
            db_pos = db.query(Position).first()
            if db_pos:
                db.delete(db_pos)

            # Cleanup Active Trade Plan when closed
            db_plan = db.query(ActiveTradePlan).filter(ActiveTradePlan.symbol == pos["symbol"]).first()
            if db_plan:
                db.delete(db_plan)

            db_trade = db.query(Trade).filter(Trade.status == "OPEN").first()
            if db_trade:
                db_trade.status = "CLOSED"
                db_trade.exit_price = current_price
                db_trade.exit_timestamp = datetime.utcnow()
                db_trade.realized_pnl = full_net_pnl
                db_trade.trading_fees = total_trade_fees
            db.commit()
        except Exception as e:
            logger.error(f"Failed to persist closed position: {e}")
        finally:
            db.close()

        self.position = None
        self.active_trade_plan = None

    def increment_candle_age(self):
        if self.position:
            self.position["candles_held"] += 1

        if self.pending_setup:
            self.pending_setup["candles_waited"] += 1
            if self.pending_setup["candles_waited"] >= self.setup_expiry_candles:
                logger.info("Pending setup expired without price reaching entry zone.")
                self.pending_setup = None
