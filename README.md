# BTC/ETH Signal Bot

Phase 6 scaffold for a production-oriented FastAPI BTC/ETH signal bot.

This phase includes:
- Binance public OHLCV fetcher
- technical indicators and decision engine
- auxiliary OpenAI analyzer using `OPENAI_API_KEY`, `OPENAI_MODEL`, and optional `OPENAI_BASE_URL`
- Telegram notifier and anti-spam policy
- automatic background scheduler started with FastAPI
- startup Telegram status message with initial analysis summary
- `GET /signals`, `GET /signals/{symbol}`, and `POST /run-once`
- persisted signal state and last Telegram send state in `STATE_PATH`

## Scheduler

- Runs every `CHECK_INTERVAL_SECONDS`
- Default interval: `600`
- Starts automatically when FastAPI starts
- Scheduler exceptions are caught and logged so the API process keeps running

## Health Check

- `GET /health` returns `{"status":"ok"}`
- Safe to use as the Koyeb service health check path

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Docker

```bash
docker build -t tradebot .
docker run --rm -p 8000:8000 --env-file .env tradebot
```

The container listens on `0.0.0.0:8000`.

## Koyeb deployment notes

- Deploy using the included `Dockerfile`
- Expose port `8000`
- Set the health check path to `/health`
- Set required environment variables in Koyeb service settings
- Keep `CHECK_INTERVAL_SECONDS=600` unless you have a reason to change it
- Persist `/app/data` if you want signal history and Telegram send state to survive restarts
- The scheduler starts automatically with the web process; no separate worker is required

## Telegram behavior

Telegram sends only when:
- action changed, or
- dominant score changed by `TELEGRAM_SCORE_DELTA`, or
- cooldown expired and signal is still strong

The bot does not spam `HOLD` messages.

On startup, if Telegram is configured, the bot also sends:
- bot started status
- scheduler interval
- OpenAI configured status
- initial BTC/ETH analysis snapshot or startup error

## OpenAI behavior

OpenAI is auxiliary only.
- It receives a compact market snapshot plus the technical decision.
- It does not directly change the technical decision.
- The only allowed override is forcing `HOLD` when `data_quality_warning=true`.
- If OpenAI fails or is not configured, the bot continues with `AI analysis unavailable`.
- To route requests through a proxy-compatible OpenAI endpoint, set `OPENAI_BASE_URL`.
- Example proxy configuration: `OPENAI_BASE_URL=https://sub.tehuio.com`
- If you set only the root domain, the app normalizes it to `/v1` automatically for OpenAI-compatible proxies.
- If `OPENAI_BASE_URL` is set, the app uses `/v1/chat/completions` directly for maximum proxy compatibility.
- Without `OPENAI_BASE_URL`, the app tries `Responses API` first and falls back to `chat.completions` if needed.
