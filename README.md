# LLM Trading Agent

A completely self-hosted, LLM-powered cryptocurrency trading agent running continuously via Docker Compose.

## Architecture

This project strictly separates responsibilities to ensure that the LLM functions only as a strategic decision engine, while execution and risk are handled deterministically:

`Market Data (Binance) -> Feature/Indicator Engine -> Market Context Builder -> LLM Agent (OpenAI API spec) -> Deterministic Risk/Validation Engine -> Execution Engine (Paper)`

## Features
- **Multi-timeframe Analysis**: Feeds 1H, 15M, and 5M context to the LLM.
- **Strict Semantic Actions**: Prevents illogical behaviors (like holding a position when none exists).
- **Deterministic Risk Engine**: Hard checks on Risk/Reward ratio, leverage limits, and real-time safety. Stop Losses and Take Profits trigger deterministically on price ticks, independently of LLM latency.
- **Local Paper Trading Simulator**: Fully local realistic simulation approximating fees, margin locked, and PnL.

## Usage

1. Copy `.env.example` to `.env` and fill in the values:
   - Configure `LLM_BASE_URL` and `LLM_API_KEY` for your preferred provider.
2. Build and run locally or on a VPS:
   `docker compose up -d --build`

## Running Tests
Run tests via `pytest`:
`pytest tests/`
