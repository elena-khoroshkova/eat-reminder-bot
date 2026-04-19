from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def validate_time_str(t: str) -> None:
    if not _TIME_RE.match(t):
        raise ValueError(f"Invalid time '{t}', expected HH:MM (00:00-23:59)")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ReminderKey:
    user_id: int
    meal_slot: int  # 1..3


def meal_name(slot: int) -> str:
    return {1: "Meal 1", 2: "Meal 2", 3: "Meal 3"}.get(slot, f"Meal {slot}")


class ReminderScheduler:
    def __init__(self, tz: str):
        self._scheduler = AsyncIOScheduler(timezone=None if tz == "local" else tz)

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    def upsert_daily_meals(
        self,
        *,
        user_id: int,
        times: tuple[str, str, str],
        on_meal: callable,
    ) -> None:
        for slot, t in enumerate(times, start=1):
            validate_time_str(t)
            hh, mm = t.split(":")
            job_id = f"meal:{user_id}:{slot}"
            self._scheduler.add_job(
                on_meal,
                trigger=CronTrigger(hour=int(hh), minute=int(mm)),
                id=job_id,
                replace_existing=True,
                kwargs={"user_id": user_id, "meal_slot": slot},
                max_instances=1,
                coalesce=True,
            )

    def clear_daily_meals(self, *, user_id: int) -> None:
        for slot in (1, 2, 3):
            job_id = f"meal:{user_id}:{slot}"
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass

    def start_nagging(
        self,
        *,
        user_id: int,
        meal_slot: int,
        every_minutes: int,
        on_nag: callable,
    ) -> None:
        job_id = f"nag:{user_id}"
        self._scheduler.add_job(
            on_nag,
            trigger=IntervalTrigger(minutes=every_minutes),
            id=job_id,
            replace_existing=True,
            kwargs={"user_id": user_id, "meal_slot": meal_slot},
            max_instances=1,
            coalesce=True,
        )

    def stop_nagging(self, *, user_id: int) -> None:
        job_id = f"nag:{user_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

