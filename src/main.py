import asyncio
import time
import json
from src.config.settings import settings
from src.market.binance import BinanceMarketDataAdapter
from src.market.candles import MultiTimeframeState
from src.features.market_context import MarketContextBuilder
from src.agent.client import LLMClient
from src.risk.validation import DecisionValidator
from src.risk.manager import RiskManager
from src.execution.executor import LocalPaperExecutor
from src.monitoring.logging import setup_logging, logger
from src.storage.database import engine, SessionLocal
from src.storage.models import Base
from src.storage.models import Decision, Trade, Position, SystemEvent

class TradingBot:
    def __init__(self):
        self.market_adapter = BinanceMarketDataAdapter()

        self.primary_symbol = settings.SYMBOL
        self.mtf_state = MultiTimeframeState(self.primary_symbol, limit=settings.HISTORICAL_CANDLE_LIMIT)
        self.context_builder = MarketContextBuilder(llm_candle_context=settings.LLM_CANDLE_CONTEXT)

        self.llm_client = LLMClient(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL
        )
        self.validator = DecisionValidator()
        self.risk_manager = RiskManager()
        self.executor = None # Will be initialized after DB creation

        self.is_running = False
        self.decision_lock = asyncio.Lock()

    def _touch_health_file(self):
        """Update health file to prove the main loop and ws are alive."""
        try:
            with open("/tmp/health", "w") as f:
                f.write(str(time.time()))
        except Exception as e:
            pass

    def log_event(self, event_type: str, message: str):
        db = SessionLocal()
        try:
            evt = SystemEvent(event_type=event_type, message=message)
            db.add(evt)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to log event to DB: {e}")
        finally:
            db.close()

    async def initialize(self):
        setup_logging()
        logger.info(f"Initializing Trading Bot in {settings.TRADING_MODE} mode.")
        if settings.TRADING_MODE == "live":
            raise ValueError("Live trading is not implemented/enabled in v1.")

        # Init DB
        Base.metadata.create_all(bind=engine)
        self.executor = LocalPaperExecutor()
        self.log_event("STARTUP", f"Started in {settings.TRADING_MODE} mode for {self.primary_symbol}")

        # Fetch historical data
        logger.info(f"Fetching historical data for {self.primary_symbol}")
        try:
            h1_candles = await self.market_adapter.fetch_historical_candles(self.primary_symbol, "1H", settings.HISTORICAL_CANDLE_LIMIT)
            self.mtf_state.initialize_history("1H", h1_candles)

            m15_candles = await self.market_adapter.fetch_historical_candles(self.primary_symbol, "15M", settings.HISTORICAL_CANDLE_LIMIT)
            self.mtf_state.initialize_history("15M", m15_candles)

            m5_candles = await self.market_adapter.fetch_historical_candles(self.primary_symbol, "5M", settings.HISTORICAL_CANDLE_LIMIT)
            self.mtf_state.initialize_history("5M", m5_candles)
            logger.info("Historical data fetched successfully.")
        except Exception as e:
            logger.error(f"Critical error fetching historical data: {e}")
            raise e

    async def on_market_update(self, data: dict):
        # Healthcheck update
        self._touch_health_file()

        if data["type"] == "mark_price":
            price = data["price"]
            self.mtf_state.update_mark_price(price)
            # Real-time deterministic safety check
            self.executor.update_price(price)

        elif data["type"] == "candle":
            tf = data["timeframe"]
            # Important: We only update the state for the specific timeframe that received an update.
            # 1H and 15M closed states will ONLY update when the real 1H and 15M candles close from Binance.
            self.mtf_state.update_candle(tf, data)

            # The decision cycle is strictly synchronized to the close of 5M candles.
            if tf == "5M" and data["is_closed"]:
                self.executor.increment_candle_age()
                asyncio.create_task(self.run_decision_cycle())

    async def run_decision_cycle(self):
        # Prevent concurrent decision cycles
        if self.decision_lock.locked():
            logger.warning("Decision cycle already running, skipping overlapping cycle.")
            return

        async with self.decision_lock:
            try:
                logger.info("--- Starting LLM Decision Cycle ---")

                # 1. Fetch recent decisions for temporal memory
                db = SessionLocal()
                try:
                    db_recent_decisions = db.query(Decision).filter(
                        Decision.symbol == self.primary_symbol,
                        Decision.is_valid == True
                    ).order_by(Decision.id.desc()).limit(5).all()

                    recent_decisions = []
                    # Reverse to chronological order (oldest first, newest last)
                    for d in reversed(db_recent_decisions):
                        recent_decisions.append({
                            "action": d.action,
                            "confidence": d.confidence,
                            "setup_type": d.setup_type,
                            "entry_zone_low": d.entry_zone_low,
                            "entry_zone_high": d.entry_zone_high,
                            "invalidation_price": d.invalidation_price,
                            "first_obstacle": d.first_obstacle,
                            "reasoning_summary": d.reasoning_summary,
                            "timestamp": d.timestamp.isoformat()
                        })
                finally:
                    db.close()

                # 2. Build Context
                current_position = self.executor.get_position()
                active_trade_plan = self.executor.active_trade_plan if current_position else None

                context = self.context_builder.build_context(
                    state=self.mtf_state,
                    position=current_position,
                    active_trade_plan=active_trade_plan,
                    recent_decisions=recent_decisions
                )
                context_json = context.model_dump_json(indent=2)

                # 3. Query LLM
                decision = await self.llm_client.get_decision(context_json)
                if not decision:
                    logger.warning("No decision returned from LLM. Skipping this cycle.")
                    # Existing position safety continues via on_market_update -> executor.update_price
                    return

                logger.info(f"LLM Decision: {decision.action} (Conf: {decision.confidence})")

                # 3. Validate
                is_valid, reason = self.validator.validate(decision, context)

                db = SessionLocal()
                try:
                    db_decision = Decision(
                        symbol=self.primary_symbol,
                        action=decision.action,
                        confidence=decision.confidence,
                        setup_type=decision.setup_type,
                        entry_zone_low=decision.entry_zone.low if decision.entry_zone else None,
                        entry_zone_high=decision.entry_zone.high if decision.entry_zone else None,
                        invalidation_price=decision.invalidation_price,
                        first_obstacle=decision.first_obstacle,
                        reasoning_summary=decision.reasoning_summary,
                        is_valid=is_valid,
                        rejection_reason=reason
                    )
                    db.add(db_decision)
                    db.commit()
                finally:
                    db.close()

                if not is_valid:
                    logger.warning(f"Decision rejected by Validator: {reason}")
                    return

                # 4. Process Action
                if decision.action == "CLOSE":
                    logger.info("Closing position based on LLM decision.")
                    self.executor.close_position(self.mtf_state.mark_price, reason="LLM_CLOSE")
                    return
                elif decision.action == "HOLD":
                    if decision.stop_loss is not None:
                        self.executor.update_stop_loss(decision.stop_loss, self.mtf_state.mark_price)
                    return
                elif decision.action == "WAIT":
                    return # Do nothing

                # 5. Risk Engine for LONG/SHORT
                is_approved, risk_reason, exec_params = self.risk_manager.calculate_position(decision, context, self.executor.available_balance)

                if not is_approved:
                    logger.warning(f"Decision rejected by Risk Manager: {risk_reason}")
                    return

                # 6. Execute
                self.executor.execute_params(exec_params)
                logger.info("--- Decision Cycle Complete ---")

            except Exception as e:
                logger.error(f"Error during decision cycle: {e}")

    async def run(self):
        await self.initialize()
        self.is_running = True

        # Connect websocket in background
        ws_task = asyncio.create_task(
            self.market_adapter.connect_websocket([self.primary_symbol], self.on_market_update)
        )

        try:
            # Keep main thread alive
            while self.is_running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Bot execution cancelled.")
        finally:
            self.is_running = False
            ws_task.cancel()
            await self.market_adapter.close()
            self.log_event("SHUTDOWN", "Bot shutdown gracefully.")

async def main():
    bot = TradingBot()
    await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user.")
