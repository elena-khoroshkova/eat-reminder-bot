from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import aiosqlite


MealSlot = Literal[1, 2, 3]


@dataclass
class UserState:
    user_id: int
    enabled: bool
    meal_time_1: str
    meal_time_2: str
    meal_time_3: str
    waiting_for_meal: MealSlot | None
    waiting_since_utc: str | None


class Storage:
    def __init__(self, db_path: str):
        self._db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_state (
                  user_id INTEGER PRIMARY KEY,
                  enabled INTEGER NOT NULL,
                  meal_time_1 TEXT NOT NULL,
                  meal_time_2 TEXT NOT NULL,
                  meal_time_3 TEXT NOT NULL,
                  waiting_for_meal INTEGER NULL,
                  waiting_since_utc TEXT NULL
                )
                """
            )
            await db.commit()

    async def upsert_user_defaults(self, user_id: int, meal_times: tuple[str, str, str]) -> UserState:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO user_state (user_id, enabled, meal_time_1, meal_time_2, meal_time_3, waiting_for_meal, waiting_since_utc)
                VALUES (?, 1, ?, ?, ?, NULL, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                  enabled=excluded.enabled,
                  meal_time_1=COALESCE(user_state.meal_time_1, excluded.meal_time_1),
                  meal_time_2=COALESCE(user_state.meal_time_2, excluded.meal_time_2),
                  meal_time_3=COALESCE(user_state.meal_time_3, excluded.meal_time_3)
                """,
                (user_id, meal_times[0], meal_times[1], meal_times[2]),
            )
            await db.commit()
        return await self.get_user(user_id)

    async def get_user(self, user_id: int) -> UserState:
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                SELECT user_id, enabled, meal_time_1, meal_time_2, meal_time_3, waiting_for_meal, waiting_since_utc
                FROM user_state
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            await cur.close()
        if not row:
            raise KeyError(f"user_id {user_id} not found")
        waiting_for_meal = row[5]
        return UserState(
            user_id=row[0],
            enabled=bool(row[1]),
            meal_time_1=row[2],
            meal_time_2=row[3],
            meal_time_3=row[4],
            waiting_for_meal=int(waiting_for_meal) if waiting_for_meal is not None else None,  # type: ignore[arg-type]
            waiting_since_utc=row[6],
        )

    async def set_enabled(self, user_id: int, enabled: bool) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE user_state SET enabled=? WHERE user_id=?", (1 if enabled else 0, user_id))
            await db.commit()

    async def set_meal_times(self, user_id: int, times: tuple[str, str, str]) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE user_state
                SET meal_time_1=?, meal_time_2=?, meal_time_3=?
                WHERE user_id=?
                """,
                (times[0], times[1], times[2], user_id),
            )
            await db.commit()

    async def set_waiting(self, user_id: int, waiting_for_meal: MealSlot | None, waiting_since_utc: str | None) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE user_state SET waiting_for_meal=?, waiting_since_utc=? WHERE user_id=?",
                (waiting_for_meal, waiting_since_utc, user_id),
            )
            await db.commit()

    async def list_enabled_users(self) -> list[UserState]:
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                SELECT user_id, enabled, meal_time_1, meal_time_2, meal_time_3, waiting_for_meal, waiting_since_utc
                FROM user_state
                WHERE enabled = 1
                """
            )
            rows = await cur.fetchall()
            await cur.close()

        users: list[UserState] = []
        for row in rows:
            waiting_for_meal = row[5]
            users.append(
                UserState(
                    user_id=row[0],
                    enabled=bool(row[1]),
                    meal_time_1=row[2],
                    meal_time_2=row[3],
                    meal_time_3=row[4],
                    waiting_for_meal=int(waiting_for_meal) if waiting_for_meal is not None else None,  # type: ignore[arg-type]
                    waiting_since_utc=row[6],
                )
            )
        return users

