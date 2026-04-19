from __future__ import annotations

from dataclasses import dataclass
import os


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    return v if v else default


@dataclass(frozen=True)
class Config:
    bot_token: str
    meal_times_default: tuple[str, str, str]
    remind_every_minutes: int
    tz: str
    food_confidence: float
    db_path: str


def load_config() -> Config:
    bot_token = _env("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required (export BOT_TOKEN=...)")

    meal_times = _env("MEAL_TIMES", "09:00,14:00,20:00")
    parts = [p.strip() for p in meal_times.split(",") if p.strip()]
    if len(parts) != 3:
        raise RuntimeError("MEAL_TIMES must have exactly 3 comma-separated times, e.g. 09:00,14:00,20:00")

    remind_every = int(_env("REMIND_EVERY_MINUTES", "10") or "10")
    tz = _env("TZ", "local") or "local"
    food_confidence = float(_env("FOOD_CONFIDENCE", "0.25") or "0.25")

    return Config(
        bot_token=bot_token,
        meal_times_default=(parts[0], parts[1], parts[2]),
        remind_every_minutes=remind_every,
        tz=tz,
        food_confidence=food_confidence,
        db_path=_env("DB_PATH", "data.sqlite3") or "data.sqlite3",
    )

