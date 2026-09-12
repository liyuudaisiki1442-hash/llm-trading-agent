# AGENTS.md

Instructions for future AI coding agents maintaining or modifying this project:

- **Never commit secrets**: Do not expose `.env` files or hardcode API keys.
- **Never enable live trading by default**: `TRADING_MODE=paper` must always remain the default fallback.
- **Never modify risk limits silently**: The Risk Engine constraints (e.g., Max Leverage, Risk/Reward thresholds) must remain strict and deterministically calculated.
- **Never bypass the risk manager**: The LLM must not have direct control over exchange execution or final quantity sizes without validation.
- **Infrastructure changes**: Modifications to SQLAlchemy schemas or Exchange adapters must not change the underlying strategy logic.
- **Testing**: You must run `pytest tests/` before submitting changes and ensure tests are passing.
