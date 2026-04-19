# Eat Reminder Telegram Bot

Telegram bot that reminds you to eat **3 times a day**. For each meal reminder, it keeps pinging until you reply with a **photo that is classified as food**.

## Features

- 3 scheduled reminders per day (configurable)
- “Nag mode”: repeat reminder every N minutes until a food photo is received
- Local food detection (no paid APIs): image is classified and accepted only if it looks like food
- Simple persistence in SQLite (survives restarts)

## Setup

1) Create a Telegram bot token via **@BotFather**.

2) Create a venv and install dependencies:

```bash
cd /Users/xoroshok/eat-reminder-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3) Create `.env` (or export env vars) with at least:

```bash
export BOT_TOKEN="PASTE_YOUR_TOKEN"
```

Optional settings:

- `MEAL_TIMES`: comma-separated HH:MM times, local time. Default: `09:00,14:00,20:00`
- `REMIND_EVERY_MINUTES`: repeat interval while waiting. Default: `10`
- `TZ`: timezone name. Default: `local` (uses your machine local time)
- `FOOD_CONFIDENCE`: minimum probability to accept a photo as food. Default: `0.25`

Example:

```bash
export MEAL_TIMES="08:30,13:00,19:30"
export REMIND_EVERY_MINUTES="7"
export FOOD_CONFIDENCE="0.30"
```

4) Run:

```bash
python -m app
```

## Commands

- `/start` — enable reminders for you
- `/status` — show current state (waiting/idle + times)
- `/settimes 09:00 14:00 20:00` — update your 3 meal times
- `/stop` — disable reminders

## Notes

- The first run will be slower because Torch may download/caches model weights (still local inference).
- If you want stronger food detection later, we can switch to a Food-101 model (better accuracy) or a paid vision API.

