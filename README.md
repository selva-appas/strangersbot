# StrangerMatch

StrangerMatch is a Telegram bot for anonymous stranger matching, casual conversation, and dating. It is designed for adults 18+ only and uses a privacy-first approach that does not expose Telegram usernames, IDs, or exact personal data unless the users choose to share that information themselves inside the match.

## Features

- Anonymous matching based on age, gender, city, preferences, and conversation mode
- SQLite-backed persistence for the initial version
- Rate-limited matching and reporting
- Admin moderation tools for bans, filtering, and stats
- Safety guidance and suspicious content warnings
- Block and report flows that terminate chats and protect privacy
- Modular architecture prepared for future PostgreSQL, Redis, and webhook support

## Requirements

- Python 3.11+
- Telegram bot token from BotFather
- SQLite support (built in)
- `python-telegram-bot`
- `python-dotenv`
- `pytest`

## Python installation

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Telegram BotFather setup

1. Open Telegram and message `@BotFather`.
2. Create a new bot using `/newbot`.
3. Save the bot token you are given.
4. Copy the token into a `.env` file in the project root.

## Environment configuration

Create a `.env` file (not committed to source control) based on `.env.example`:

```env
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
ADMIN_IDS=123456789
BOT_DB_PATH=bot.db
```

## Installation

```bash
pip install -r requirements.txt
```

## Running the project

```bash
python bot.py
```

## Railway deployment

This repository is ready to deploy as a Python service on Railway.

1. Push the project to GitHub.
2. Create a new Railway project and connect the repository.
3. In the Railway service settings, set the start command to:

```bash
python bot.py
```

4. Add these environment variables in Railway:

```env
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
ADMIN_IDS=123456789
BOT_DB_PATH=bot.db
```

Railway will use the included Python runtime configuration and start the bot as a long-running polling service.

## Windows instructions

```powershell
.venv\Scripts\activate
python bot.py
```

Or run the helper:

```powershell
run_windows.bat
```

## Linux instructions

```bash
source .venv/bin/activate
python bot.py
```

Or run the helper:

```bash
chmod +x run_linux.sh
./run_linux.sh
```

## Admin configuration

Set the admin Telegram numeric IDs in `.env` using the `ADMIN_IDS` variable. Example:

```env
ADMIN_IDS=123456789,987654321
```

Only those users can access admin commands like `/admin_stats`, `/admin_report`, `/ban`, and `/unban`.

## Database information

The bot uses SQLite initially. The database path defaults to `bot.db` and can be overridden with `BOT_DB_PATH`.

The schema includes:

- `users`
- `blocks`
- `reports`
- `moderation_actions`
- `rate_events`
- `user_sessions`

The project includes migration logic for older databases that may have an `age` column but no `date_of_birth`.

## Security considerations

- Never log the bot token or private Telegram data unnecessarily.
- Use parameterized SQL queries.
- Validate all input.
- Keep the rate limiter and moderation checks modular for future migration to Redis or a moderation service.
- Do not treat DOB entry as identity verification.

## Privacy considerations

- Only ask for a city or general area, not a home address or GPS coordinates.
- Never reveal Telegram usernames, IDs, or exact private contact details unless someone voluntarily shares them in chat.
- The service is for adults 18+ only.
- The bot does not verify that another user is truthful.

## Production deployment recommendations

Before production use, consider:

- Hosting behind HTTPS and a public webhook endpoint
- Using PostgreSQL for multi-instance deployments
- Using Redis for rate limiting and sessions
- Adding a professional age-assurance and identity-verification provider if legally required
- Using a professional content moderation service for image and text checks
- Logging and audit trails for moderation actions
- Containerization with Docker

## Troubleshooting

- If the bot does not start, check that `.env` exists and contains a valid `TELEGRAM_BOT_TOKEN`.
- If you get SQLite errors, remove the existing database file and let it recreate.
- If a user is under 18, they must enter a valid date of birth showing they are adults.
- If a message type cannot be relayed, the bot sends a warning instead of crashing.

## Important safety limitation

Entering a date of birth is not equivalent to verified identity or verified age. This is a self-declared age-assurance flow for adults 18+ only. A public dating platform should consider a professional age-assurance or identity-verification provider before launch if legally or operationally required.

## License

This project is intended for educational and prototype use in a local environment. Adjust configuration and deployment choices for production compliance and legal requirements.
