# EchoVerse AI — Telegram Voice Bot

A production-ready Telegram bot (aiogram 3.x) for text-to-speech, voice
cloning, credits, and referrals, backed by **Cartesia** as the voice
provider. Cartesia is used purely as backend infrastructure — its name never
appears in user-facing text, buttons, or errors.

## Features

- 🎙 Text-to-speech generation with a selected voice, speed, and volume
- 🎭 Dynamic voice library pulled live from the provider (no hardcoded list),
  with category browsing, language filter, and search
- 🧬 Instant voice cloning from a short audio sample, with explicit consent
- 👤 Per-user voice management (rename, delete, select)
- 💰 Atomic credit system with a full transaction ledger
- 🎁 Referral system with self-referral/double-reward protection
- 📜 Generation history with replay and regenerate
- ⚙️ Per-user settings (language, default voice, speed, volume)
- 🛠 Admin panel: stats, user list, credit adjustments, broadcast

## Setup

1. **Python 3.11+** recommended.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the environment template and fill in your values:
   ```bash
   cp .env.example .env
   ```
   At minimum you need:
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `CARTESIA_API_KEY` — your Cartesia API key
   - `ADMIN_IDS` — your Telegram numeric user ID(s), comma-separated
4. Run the bot:
   ```bash
   python -m app.main
   ```

The SQLite database (`voicebot.db`) is created automatically on first run.
To move to PostgreSQL later, just change `DATABASE_URL` in `.env` (e.g.
`postgresql+asyncpg://user:pass@host:5432/db`) and install `asyncpg`
(uncomment it in `requirements.txt`) — the code doesn't need to change.

## Project layout

```
app/
├── main.py              # entrypoint: bot, dispatcher, router wiring
├── config.py             # all settings, loaded from environment
├── middlewares.py         # injects DB session + current user into handlers
├── database/
│   ├── database.py        # engine, session, get_or_create_user
│   └── models.py           # SQLAlchemy models
├── handlers/               # thin, one file per feature area
├── keyboards/               # inline keyboard builders
├── services/
│   ├── voice_api.py          # the ONLY module that talks to Cartesia
│   ├── credits.py             # atomic credit ledger
│   └── referral.py             # referral linking + reward logic
├── states/                      # aiogram FSM states
└── utils/                        # callback data, validation, helpers
```

## Notes on the voice provider integration

`app/services/voice_api.py` is the single point of contact with Cartesia.
It was built and verified against the **installed** `cartesia` Python SDK
(v4.x) — method signatures were checked with `inspect.signature` against the
real package, not assumed from documentation snippets, since the SDK has
had breaking changes across versions. If you upgrade the `cartesia` package
later, run:

```bash
python -c "import inspect; from cartesia import AsyncCartesia; c = AsyncCartesia(api_key='x'); print(inspect.signature(c.tts.generate)); print(inspect.signature(c.voices.clone))"
```

and diff against the current implementation before deploying, in case the
SDK's parameter names change again.

Generation speed and volume are sent via Cartesia's `generation_config`
(`sonic-3` model family); if you switch to an older model that doesn't
support it, drop or adapt that field in `generate_speech()`.

## Testing checklist

See the task brief's 20-point checklist. Before going live, at minimum
verify: `/start` + referral capture, voice selection, generation + credit
deduction, insufficient-credit blocking, cloning end-to-end, my-voices
rename/delete, history replay, settings persistence, admin panel access
(only for `ADMIN_IDS`), broadcast, and that the bot recovers cleanly after a
restart (all state that matters is in the database, not in memory).
