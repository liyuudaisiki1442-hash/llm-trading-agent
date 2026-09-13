from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Core
    TRADING_MODE: str = Field(default="paper", description="paper or live")
    SYMBOL: str = Field(default="BTCUSDT")

    # Paper Trading
    PAPER_INITIAL_BALANCE: float = Field(default=10000.0)

    # Market Data
    HISTORICAL_CANDLE_LIMIT: int = Field(default=500)

    # LLM
    LLM_BASE_URL: str = Field(default="")
    LLM_API_KEY: str = Field(default="")
    LLM_MODEL: str = Field(default="")
    LLM_CANDLE_CONTEXT: int = Field(default=30)
    DECISION_INTERVAL_MINUTES: int = Field(default=5)

    # Exchange (Binance)
    BINANCE_API_KEY: str = Field(default="")
    BINANCE_API_SECRET: str = Field(default="")

    # Risk
    MAX_LEVERAGE: int = Field(default=1)
    RISK_PER_TRADE: float = Field(default=0.01)
    MAX_POSITIONS: int = Field(default=1)
    MAX_DAILY_LOSS: float = Field(default=0.05)

    # DB
    DATABASE_URL: str = Field(default="sqlite:///trading_agent.db")

settings = Settings()
