from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .config import load_config
from .food_classifier import FoodClassifier
from .reminders import ReminderScheduler, meal_name, now_utc_iso
from .storage import Storage
from .reminders import validate_time_str


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eat-reminder-bot")


def _parse_settimes_args(text: str) -> tuple[str, str, str]:
    parts = text.split()
    if len(parts) != 4:
        raise ValueError("Usage: /settimes 09:00 14:00 20:00")
    t1, t2, t3 = parts[1], parts[2], parts[3]
    validate_time_str(t1)
    validate_time_str(t2)
    validate_time_str(t3)
    return (t1, t2, t3)


async def main_async() -> None:
    cfg = load_config()

    storage = Storage(cfg.db_path)
    await storage.init()

    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher()

    scheduler = ReminderScheduler(cfg.tz)
    classifier = FoodClassifier()

    async def restore_schedules() -> None:
        """
        On Railway (and other hosts), the process may restart/redeploy.
        Daily meal jobs are in-memory, so we re-create them from SQLite on startup.
        """
        users = await storage.list_enabled_users()
        for st in users:
            scheduler.upsert_daily_meals(
                user_id=st.user_id,
                times=(st.meal_time_1, st.meal_time_2, st.meal_time_3),
                on_meal=send_reminder,
            )
            if st.waiting_for_meal is not None:
                scheduler.start_nagging(
                    user_id=st.user_id,
                    meal_slot=st.waiting_for_meal,
                    every_minutes=cfg.remind_every_minutes,
                    on_nag=send_nag,
                )

    async def send_reminder(user_id: int, meal_slot: int) -> None:
        try:
            st = await storage.get_user(user_id)
        except KeyError:
            return

        if not st.enabled:
            return

        # If already waiting for a previous meal, don't start a new one; keep nagging.
        if st.waiting_for_meal is None:
            await storage.set_waiting(user_id, meal_slot, now_utc_iso())
            scheduler.start_nagging(
                user_id=user_id,
                meal_slot=meal_slot,
                every_minutes=cfg.remind_every_minutes,
                on_nag=send_nag,
            )

        await bot.send_message(
            user_id,
            f"🍽️ Time to eat ({meal_name(meal_slot)}).\n"
            f"Send a photo of your food to stop the reminders.",
        )

    async def send_nag(user_id: int, meal_slot: int) -> None:
        try:
            st = await storage.get_user(user_id)
        except KeyError:
            scheduler.stop_nagging(user_id=user_id)
            return

        if not st.enabled:
            scheduler.stop_nagging(user_id=user_id)
            return

        if st.waiting_for_meal is None:
            scheduler.stop_nagging(user_id=user_id)
            return

        await bot.send_message(
            user_id,
            f"⏰ Reminder: please eat and send a food photo to confirm ({meal_name(st.waiting_for_meal)}).",
        )

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        user_id = message.from_user.id
        st = await storage.upsert_user_defaults(user_id, cfg.meal_times_default)
        await storage.set_enabled(user_id, True)

        # schedule jobs for this user
        scheduler.upsert_daily_meals(
            user_id=user_id,
            times=(st.meal_time_1, st.meal_time_2, st.meal_time_3),
            on_meal=send_reminder,
        )

        await message.answer(
            "✅ Reminders enabled.\n\n"
            f"Default times: {st.meal_time_1}, {st.meal_time_2}, {st.meal_time_3}\n"
            "Use /settimes to change them.\n"
            "When you get a reminder, send a food photo to stop it."
        )

    @dp.message(Command("stop"))
    async def cmd_stop(message: Message) -> None:
        user_id = message.from_user.id
        try:
            await storage.get_user(user_id)
        except KeyError:
            await message.answer("You were not enabled yet. Use /start.")
            return

        await storage.set_enabled(user_id, False)
        await storage.set_waiting(user_id, None, None)
        scheduler.clear_daily_meals(user_id=user_id)
        scheduler.stop_nagging(user_id=user_id)
        await message.answer("🛑 Reminders disabled.")

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        user_id = message.from_user.id
        try:
            st = await storage.get_user(user_id)
        except KeyError:
            await message.answer("Not set up yet. Use /start.")
            return

        waiting = f"waiting for {meal_name(st.waiting_for_meal)}" if st.waiting_for_meal else "idle"
        enabled = "enabled" if st.enabled else "disabled"
        await message.answer(
            f"Status: {enabled}, {waiting}\n"
            f"Times: {st.meal_time_1}, {st.meal_time_2}, {st.meal_time_3}"
        )

    @dp.message(Command("settimes"))
    async def cmd_settimes(message: Message) -> None:
        user_id = message.from_user.id
        try:
            await storage.get_user(user_id)
        except KeyError:
            await message.answer("Use /start first.")
            return

        try:
            times = _parse_settimes_args(message.text or "")
        except Exception as e:
            await message.answer(str(e))
            return

        await storage.set_meal_times(user_id, times)
        st = await storage.get_user(user_id)

        if st.enabled:
            scheduler.upsert_daily_meals(
                user_id=user_id,
                times=(st.meal_time_1, st.meal_time_2, st.meal_time_3),
                on_meal=send_reminder,
            )

        await message.answer(f"✅ Updated times: {st.meal_time_1}, {st.meal_time_2}, {st.meal_time_3}")

    @dp.message(F.photo)
    async def on_photo(message: Message) -> None:
        user_id = message.from_user.id
        try:
            st = await storage.get_user(user_id)
        except KeyError:
            await message.answer("Use /start first.")
            return

        if not st.enabled:
            await message.answer("Reminders are disabled. Use /start.")
            return

        if st.waiting_for_meal is None:
            await message.answer("Photo received, but I’m not currently waiting for a meal reminder.")
            return

        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        image_bytes = await bot.download_file(file.file_path)
        data = image_bytes.read()

        result = classifier.check_food(data, min_confidence=cfg.food_confidence, topk=5)
        if not result.is_food:
            top = ", ".join([f"{lbl} ({p:.0%})" for lbl, p in result.top])
            await message.answer(
                "❌ I don't think this is food.\n"
                f"Top guess: {result.best_label} ({result.best_prob:.0%})\n"
                f"Details: {top}\n\n"
                "Please send a clearer photo of your food."
            )
            return

        # success: stop nagging + clear waiting
        meal_slot = st.waiting_for_meal
        await storage.set_waiting(user_id, None, None)
        scheduler.stop_nagging(user_id=user_id)
        await message.answer(f"✅ Food confirmed for {meal_name(meal_slot)}. Nice!")

    @dp.message()
    async def fallback(message: Message) -> None:
        if message.text and message.text.startswith("/"):
            await message.answer("Unknown command. Try /start, /status, /settimes, /stop.")
            return
        await message.answer("Send a photo of your food when I remind you to eat.")

    scheduler.start()
    await restore_schedules()

    logger.info("Bot started.")
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(main_async())

