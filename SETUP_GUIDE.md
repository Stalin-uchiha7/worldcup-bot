# ⚽ World Cup 2026 Personal Telegram Bot — Setup Guide

## What You'll Get
- ⏰ Reminder 15 min before every match
- 🟢 Kick-off notification
- ⚽ Goal alerts (scorer name + minute)
- 🟨🟥 Yellow & Red card alerts
- 🔶 Half-time score
- 🏁 Full-time final score + winner

---

## Step 1 — Get Your Telegram Bot Token (2 min)

1. Open Telegram → search **@BotFather**
2. Send: `/newbot`
3. Name it: `My World Cup 2026`
4. Username: `mywc2026_yourname_bot`
5. **Copy the TOKEN** (looks like: `7123456789:AAHxxxxxx`)

---

## Step 2 — Get Your Telegram Chat ID (1 min)

1. Open Telegram → search **@userinfobot**
2. Send any message (e.g. `hi`)
3. It replies with your **Id** number → copy it (e.g. `987654321`)

---

## Step 3 — Get Free Football API Key (2 min)

1. Go to: https://www.api-football.com
2. Click **Sign Up** → use email
3. Go to Dashboard → copy your **API Key**
4. Free tier = 100 requests/day ✅ (enough for live monitoring)

---

## Step 4 — Deploy on Railway (FREE, recommended)

1. Go to: https://railway.app → Sign up with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Upload these files to a GitHub repo first:
   - `bot.py`
   - `requirements.txt`
   - `railway.toml`
4. Connect the repo on Railway
5. Go to **Variables** tab → add these 3:

| Variable Name      | Value                        |
|--------------------|------------------------------|
| `TELEGRAM_TOKEN`   | Your token from BotFather    |
| `CHAT_ID`          | Your ID from @userinfobot    |
| `FOOTBALL_API_KEY` | Your key from api-football   |

6. Click **Deploy** → Done! 🚀

---

## Step 4 (Alternative) — Deploy on Render (FREE)

1. Go to: https://render.com → Sign up with GitHub
2. Push files to GitHub repo
3. Click **New → Background Worker**
4. Connect your GitHub repo
5. Add the same 3 environment variables
6. Click **Deploy**

---

## Step 5 — Test It

Send `/start` to your bot on Telegram.
You should receive:
> 🤖 World Cup 2026 Bot is ON! ⚽ You'll get goal alerts...

---

## How It Works

```
Every 30 sec (live match)  → checks goals, cards, status
Every 2 min (no live match) → checks for upcoming matches
15 min before kick-off      → sends you a reminder
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No messages | Check TELEGRAM_TOKEN and CHAT_ID are correct |
| API errors | Check FOOTBALL_API_KEY, free limit is 100/day |
| Bot stops | Railway auto-restarts on failure |
| Wrong league | World Cup league ID is hardcoded as `1` in bot.py |

---

## Files in This Package

| File | Purpose |
|---|---|
| `bot.py` | Main bot (runs forever) |
| `requirements.txt` | Python dependencies |
| `railway.toml` | Railway deployment config |
| `render.yaml` | Render deployment config |

---

Enjoy the World Cup 2026! 🏆🌍
