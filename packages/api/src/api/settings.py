import os
from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
  development = "development"
  testing = "testing"
  production = "production"


# Support both the prefixed (golfcart_ENV, matching env_prefix) and bare (ENV) forms,
# and feed the result into Settings.ENV as its default so the env-file selection and
# the runtime environment can never disagree.
env = Environment(os.getenv("golfcart_ENV") or os.getenv("ENV") or Environment.development)
env_file = ".env.testing" if env == Environment.testing else ".env"

file_extension = ".exe" if os.name == "nt" else ""


class Settings(BaseSettings):
  ENV: Environment = env
  LOG_LEVEL: str = "DEBUG"

  CORS_ORIGINS: list[str] = Field(
    default=[
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "http://localhost:3000",
      "http://127.0.0.1:3000",
      "http://localhost:3001",
      "http://127.0.0.1:3001",
      # Electron desktop app (protocol.handle serves from app://localhost in production)
      "app://localhost",
    ]
  )
  FRONTEND_BASE_URL: str = Field(default="http://localhost:5173")

  # Database
  DATABASE_PATH: str = Field(default="./golfcart.db")

  # BMS (Daly, Bluetooth LE)
  BMS_ADDRESS: str | None = Field(default=None, description="BLE address of the BMS; skips scanning when set.")
  BMS_SCAN_TIMEOUT: float = 10.0
  BMS_CONNECT_TIMEOUT: float = 20.0
  BMS_RESPONSE_TIMEOUT: float = 5.0
  BMS_CONNECT_ATTEMPTS: int = 2
  BMS_POLL_INTERVAL_S: float = 60.0
  BMS_RECONNECT_BACKOFF_S: float = 20.0
  BMS_QUIET_HOURS_START_H: int = Field(default=2, description="Local hour (inclusive) the BMS stays disconnected from.")
  BMS_QUIET_HOURS_END_H: int = Field(default=9, description="Local hour (exclusive) the BMS resumes connecting at.")
  BMS_QUIET_HOURS_TZ: str = "Europe/Stockholm"
  BMS_QUIET_HOURS_CHECK_S: float = 60.0
  BMS_SIMULATOR: bool = Field(default=False, description="Simulate the BMS instead of connecting over Bluetooth; for local development.")
  BMS_SIMULATOR_CYCLE_S: float = Field(default=3600.0, description="Length of one full simulated discharge+charge cycle in seconds.")

  # Sentry
  SENTRY_DSN: str | None = None

  model_config = SettingsConfigDict(env_prefix="golfcart_", env_file_encoding="utf-8", case_sensitive=False, env_file=env_file, extra="allow")

  def get_sqlite_dsn(self, driver: str) -> str:
    return f"sqlite+{driver}:///{self.DATABASE_PATH}"

  def is_environment(self, environments: set[Environment]) -> bool:
    return self.ENV in environments

  def is_testing(self) -> bool:
    return self.is_environment({Environment.testing})

  def is_development(self) -> bool:
    return self.is_environment({Environment.development})

  def generate_frontend_url(self, path: str) -> str:
    return f"{self.FRONTEND_BASE_URL}/{path}"


settings = Settings()
