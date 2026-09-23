from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from pydantic import Field, model_validator
from datetime import time
from typing import Literal
from dotenv import dotenv_values

PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"

def current_credentials(path=None):
    """The project's .env is authoritative over inherited, possibly stale credentials."""
    import os
    values=dotenv_values(path or PROJECT_ENV)
    return tuple(str(values.get(k) or "") if k in values else os.getenv(k, "")
                 for k in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN"))

class Settings(BaseSettings):
    dhan_client_id: str = ""
    dhan_access_token: str = ""
    app_mode: str = "paper"
    live_trading_enabled: bool = False
    dhan_market_symbols: str = ""
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    web_origin: str = "http://localhost:5174"
    # Keep safe paper defaults aligned with the project contract.  The project
    # .env remains authoritative at runtime, but these values must not fall back
    # to the superseded limits when a worker/test loads settings without an env
    # file or after a clean checkout.
    max_trade_risk_rupees: float = Field(default=600,gt=0,allow_inf_nan=False)
    daily_loss_limit_rupees: float = Field(default=1200,gt=0,allow_inf_nan=False)
    hard_daily_halt_rupees: float = Field(default=1200,gt=0,allow_inf_nan=False)
    max_open_positions: int = Field(default=1,ge=1,le=2)
    min_ev_rupees: float = 0
    paper_capital: float = Field(default=30000,gt=0,allow_inf_nan=False)
    paper_only: bool = True
    paper_autostart: bool = True
    paper_collect_evidence: bool = True
    paper_strategy_mode: Literal["portfolio","orb_only"] = "portfolio"
    session_start: str = "09:15"
    entry_cutoff: str = "14:30"
    session_exit: str = "15:05"
    max_quote_age_seconds: int = Field(default=2,ge=1,le=30)
    max_spread_pct: float = Field(default=.03,gt=0,lt=1,allow_inf_nan=False)
    max_correlated_risk_rupees: float = Field(default=600,gt=0,allow_inf_nan=False)
    monthly_profit_target: float = Field(default=20000,gt=0,allow_inf_nan=False)
    monthly_profit_target_basis: Literal["gross", "net"] = "gross"
    learning_min_train_trades: int = 60
    learning_min_context_trades: int = Field(default=20,gt=0)
    learning_min_validation_trades: int = 30
    learning_min_validation_days: int = 10
    strategy_version: str = "orb-retest-v1"
    planned_daily_loss_rupees: float = Field(default=1000,gt=0,allow_inf_nan=False)
    emergency_execution_reserve_rupees: float = Field(default=200,ge=0,allow_inf_nan=False)
    max_premium_commitment_rupees: float = Field(default=24000,gt=0,allow_inf_nan=False)
    cash_reserve_rupees: float = Field(default=6000,ge=0,allow_inf_nan=False)
    max_entry_attempts: int = Field(default=3,ge=1)
    max_losing_trades: int = Field(default=2,ge=1)
    exit_cooldown_minutes: int = Field(default=5,ge=0)
    weekly_loss_pause_rupees: float = Field(default=1700,gt=0,allow_inf_nan=False)
    drawdown_pause_rupees: float = Field(default=2550,gt=0,allow_inf_nan=False)

    # LLM Integration (OpenRouter)
    openrouter_api_key: str = Field(default="", description="OpenRouter API key for LLM integration")
    openrouter_model: str = Field(default="nvidia/nemotron-3-ultra-550b-a55b:free")
    llm_enabled: bool = Field(default=False)
    llm_timeout_seconds: int = Field(default=30, ge=5, le=120)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    # Optional paper-account notifications. Telegram is never an execution
    # dependency and has no order authority.
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_timeout_seconds: int = Field(default=10, ge=2, le=30)

    model_config = SettingsConfigDict(env_file=(str(PROJECT_ENV), ".env"), extra="ignore")

    @model_validator(mode="after")
    def validate_limits(self):
        if not self.max_trade_risk_rupees<=self.daily_loss_limit_rupees<=self.hard_daily_halt_rupees:
            raise ValueError("Trade risk must not exceed daily loss cap, and daily cap must not exceed hard halt")
        if self.max_correlated_risk_rupees>self.daily_loss_limit_rupees:
            raise ValueError("Correlated risk must not exceed daily loss cap")
        if not time.fromisoformat(self.session_start)<time.fromisoformat(self.entry_cutoff)<time.fromisoformat(self.session_exit):
            raise ValueError("Session start, entry cutoff and exit must be ordered")
        return self

settings = Settings()
settings.dhan_client_id,settings.dhan_access_token=current_credentials()
