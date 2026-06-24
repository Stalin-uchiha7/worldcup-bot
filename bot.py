import os
import time
import requests
import json
import asyncio
import threading
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
FD_TOKEN       = os.environ.get("FOOTBALLDATA_TOKEN")

HEADERS  = {"X-Auth-Token": FD_TOKEN}
BASE_URL = "https://api.football-data.org/v4"

WC_CODE = "WC"


POLL_INTERVAL_LIVE = 30
POLL_INTERVAL_IDLE = 120

STATE_FILE = "state.json"

# ─── CACHE ─────────────────────────────────────────────────────────────────────
CACHE = {}
CACHE_DURATION = 300  # 5 minutes

def cache_get(key: str):
    if key in CACHE:
        data, timestamp = CACHE[key]
        if time.time() - timestamp < CACHE_DURATION:
            return data
    return None

def cache_set(key: str, data):
    CACHE[key] = (data, time.time())

# ─── FLAGS ─────────────────────────────────────────────────────────────────────
FLAGS = {
    "Brazil": "🇧🇷", "Argentina": "🇦🇷", "France": "🇫🇷", "Germany": "🇩🇪",
    "Spain": "🇪🇸", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Portugal": "🇵🇹", "Netherlands": "🇳🇱",
    "Italy": "🇮🇹", "Belgium": "🇧🇪", "Croatia": "🇭🇷", "Uruguay": "🇺🇾",
    "USA": "🇺🇸", "Mexico": "🇲🇽", "Canada": "🇨🇦", "Japan": "🇯🇵",
    "Korea Republic": "🇰🇷", "Australia": "🇦🇺", "Senegal": "🇸🇳", "Morocco": "🇲🇦",
    "Ghana": "🇬🇭", "Egypt": "🇪🇬", "Tunisia": "🇹🇳", "Saudi Arabia": "🇸🇦",
    "IR Iran": "🇮🇷", "Qatar": "🇶🇦", "Ecuador": "🇪🇨", "Colombia": "🇨🇴",
    "Switzerland": "🇨🇭", "Denmark": "🇩🇰", "Sweden": "🇸🇪", "Norway": "🇳🇴",
    "Poland": "🇵🇱", "Serbia": "🇷🇸", "Ukraine": "🇺🇦", "Türkiye": "🇹🇷",
    "Czechia": "🇨🇿", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Austria": "🇦🇹",
    "Bosnia and Herzegovina": "🇧🇦", "Paraguay": "🇵🇾",
    "Honduras": "🇭🇳", "Costa Rica": "🇨🇷", "Panama": "🇵🇦",
    "Haiti": "🇭🇹", "Curaçao": "🇨🇼", "Iraq": "🇮🇶", "Jordan": "🇯🇴",
    "Algeria": "🇩🇿", "Cabo Verde": "🇨🇻", "Cape Verde": "🇨🇻",
    "New Zealand": "🇳🇿", "Uzbekistan": "🇺🇿", "South Africa": "🇿🇦",
    "Côte d'Ivoire": "🇨🇮", "Ivory Coast": "🇨🇮", "Congo DR": "🇨🇩",
}

def flag(name: str) -> str:
    return FLAGS.get(name, "🏳️")

def match_header(m: dict) -> str:
    """Works with football-data.org match structure."""
    h  = m.get("homeTeam", {}).get("name", "") or m.get("teams", {}).get("home", {}).get("name", "")
    a  = m.get("awayTeam", {}).get("name", "") or m.get("teams", {}).get("away", {}).get("name", "")
    score = m.get("score", {})
    ft    = score.get("fullTime", {})
    ht_s  = score.get("halfTime", {})
    gs = ft.get("home") if ft.get("home") is not None else (ht_s.get("home") or 0)
    ga = ft.get("away") if ft.get("away") is not None else (ht_s.get("away") or 0)
    gs = gs or 0
    ga = ga or 0
    return f"{flag(h)} <b>{h}</b> {gs} – {ga} <b>{a}</b> {flag(a)}"

def utc_to_ist(value) -> str:
    """Accepts Unix timestamp (int) or ISO datetime string."""
    try:
        if isinstance(value, str):
            dt_utc = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt_utc = datetime.fromtimestamp(value, tz=timezone.utc)
        total_minutes = dt_utc.hour * 60 + dt_utc.minute + 330
        ist_h = (total_minutes // 60) % 24
        ist_m = total_minutes % 60
        return f"{ist_h:02d}:{ist_m:02d} IST"
    except Exception:
        return "N/A IST"

def get_match_ts(m: dict) -> int:
    """Get unix timestamp from a football-data.org match."""
    try:
        return int(datetime.fromisoformat(m["utcDate"].replace("Z","+00:00")).timestamp())
    except Exception:
        return 0

def get_home_name(m: dict) -> str:
    return m.get("homeTeam", {}).get("name", "") or m.get("teams", {}).get("home", {}).get("name", "")

def get_away_name(m: dict) -> str:
    return m.get("awayTeam", {}).get("name", "") or m.get("teams", {}).get("away", {}).get("name", "")

def get_score(m: dict):
    ft = m.get("score", {}).get("fullTime", {})
    return ft.get("home") or 0, ft.get("away") or 0

# ─── API CALLS ─────────────────────────────────────────────────────────────────
def api_get(path: str, params: dict) -> dict:
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=15)
        # 👇 ADD THESE DIAGNOSTIC PRINTS TEMPORARILY
        print(f"📡 API CALL: {path} with params {params}")
        print(f"📦 RAW RESPONSE: {r.text}")
        return r.json()
    except Exception as e:
        print(f"❌ Network/JSON Error: {e}")
        print(f"[API error] {e}")
        return {}

def get_live_fixtures() -> list:
    # NO cache for live — must be real-time
    data = api_get(f"/competitions/{WC_CODE}/matches", {"status": "IN_PLAY,PAUSED"})
    return data.get("matches", [])

def get_fixtures_by_date(date_str: str) -> list:
    cache_key = f"fixtures_{date_str}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    data = api_get(f"/competitions/{WC_CODE}/matches", {"dateFrom": date_str, "dateTo": date_str})
    result = data.get("matches", [])
    cache_set(cache_key, result)
    return result

def get_todays_fixtures() -> list:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return get_fixtures_by_date(today)

def get_tomorrows_fixtures() -> list:
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    return get_fixtures_by_date(tomorrow)

def get_fixture_events(fixture_id: int) -> list:
    cache_key = f"events_{fixture_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    result = api_get(f"/matches/{fixture_id}").get("goals", [])
    cache_set(cache_key, result)
    return result

def get_top_scorers() -> list:
    cache_key = "top_scorers"
    cached = cache_get(cache_key)
    if cached:
        return cached
    result = api_get(f"/competitions/{WC_CODE}/scorers", {"limit": 10}).get("scorers", [])
    cache_set(cache_key, result)
    return result

def get_top_assists() -> list:
    cache_key = "top_assists"
    cached = cache_get(cache_key)
    if cached:
        return cached
    result = api_get(f"/competitions/{WC_CODE}/scorers", {"limit": 10}).get("scorers", [])  # assists from same endpoint
    cache_set(cache_key, result)
    return result

def get_standings() -> list:
    cache_key = "standings"
    cached = cache_get(cache_key)
    if cached:
        return cached
    data = api_get(f"/competitions/{WC_CODE}/standings")
    try:
        result = data.get("standings", [])
        cache_set(cache_key, result)
        return result
    except Exception:
        return []

def get_team_info(team_name: str) -> dict:
    cache_key = f"team_{team_name.lower()}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    result = api_get("/teams", {"search": team_name}).get("response", [])
    if result:
        cache_set(cache_key, result[0])
        return result[0]
    return {}

def get_team_fixtures(team_id: int) -> list:
    cache_key = f"team_fixtures_{team_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    result = api_get(f"/competitions/{WC_CODE}/matches", {"team": team_id}).get("matches", [])
    cache_set(cache_key, result)
    return result

def get_player_info(player_name: str) -> dict:
    cache_key = f"player_{player_name.lower()}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    result = api_get("/players", {"search": player_name}).get("response", [])
    if result:
        cache_set(cache_key, result[0])
        return result[0]
    return {}

def get_player_stats(player_id: int, season: int = 2026) -> dict:
    cache_key = f"player_stats_{player_id}_{season}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    result = []  # player stats endpoint not available on free tier
    if result:
        cache_set(cache_key, result[0])
        return result[0]
    return {}

def get_fixture_by_teams(team1: str, team2: str) -> dict:
    fixtures = get_todays_fixtures()
    for fix in fixtures:
        h_name = fix["teams"]["home"]["name"].lower()
        a_name = fix["teams"]["away"]["name"].lower()
        if team1.lower() in h_name and team2.lower() in a_name:
            return fix
        if team1.lower() in a_name and team2.lower() in h_name:
            return fix
    return {}

def get_finished_fixtures(limit: int = 5) -> list:
    cache_key = f"finished_fixtures_{limit}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = api_get(f"/competitions/{WC_CODE}/matches", {"dateFrom": today, "dateTo": today})
    result = data.get("matches", [])
    finished = [f for f in result if f["status"] == "FINISHED"]
    cache_set(cache_key, finished[:limit])
    return finished[:limit]

def get_statistics() -> dict:
    cache_key = "statistics"
    cached = cache_get(cache_key)
    if cached:
        return cached
    result = api_get(f"/competitions/{WC_CODE}/matches").get("matches", [])
    cache_set(cache_key, result)
    return result

# ─── TELEGRAM SEND ─────────────────────────────────────────────────────────────
async def send_message(text: str, chat_id: str = None):
    if chat_id is None:
        chat_id = CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[Telegram error] {e}")

def send(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[Telegram error] {e}")

# ─── STATE ─────────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ─── COMMAND HANDLERS ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🏆 <b>World Cup 2026 Bot</b> ⚽\n\n"
        "Welcome! Here are the available commands:\n\n"
        "📺 <b>Live & Fixtures</b>\n"
        "/live - Show live matches\n"
        "/today - Today's fixtures\n"
        "/tomorrow - Tomorrow's fixtures\n"
        "/next - Next upcoming match\n"
        "/results - Latest results\n\n"
        "📊 <b>Statistics</b>\n"
        "/topscorers - Golden Boot leaderboard\n"
        "/topassists - Assist leaderboard\n"
        "/standings - All group standings\n"
        "/stats - Tournament statistics\n\n"
        "🏟 <b>Team & Player Info</b>\n"
        "/group [name] - Specific group table\n"
        "/team [name] - Team information\n"
        "/player [name] - Player statistics\n"
        "/match [team1] vs [team2] - Match details\n\n"
        "❓ /help - Show this message"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fixtures = get_live_fixtures()
    if not fixtures:
        await update.message.reply_text("🔴 <b>No live matches at the moment</b>", parse_mode="HTML")
        return
    
    lines = ["🔴 <b>LIVE MATCHES</b>\n"]
    for m in fixtures:
        h      = get_home_name(m)
        a      = get_away_name(m)
        gh, ga = get_score(m)
        stage  = m.get("stage","").replace("_"," ").title()
        lines.append(
            f"{flag(h)} <b>{h}</b> {gh} – {ga} <b>{a}</b> {flag(a)}\n"
            f"⏱ 🔴 Live  |  📌 {stage}"
        )
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fixtures = get_todays_fixtures()
    if not fixtures:
        await update.message.reply_text("😴 <b>No World Cup matches today</b>", parse_mode="HTML")
        return
    
    lines = [f"📅 <b>TODAY'S MATCHES — {datetime.now(timezone.utc).strftime('%d %B %Y')}</b>\n"]
    lines.append(f"⚽ {len(fixtures)} match{'es' if len(fixtures) != 1 else ''} today\n")
    
    for m in sorted(fixtures, key=lambda f: f.get("utcDate", "")):
        h      = get_home_name(m)
        a      = get_away_name(m)
        stage  = m.get("stage", "").replace("_", " ").title()
        venue  = m.get("venue", "") or ""
        status = m["status"]
        ist_time = utc_to_ist(m["utcDate"])
        
        if status in ("TIMED", "SCHEDULED"):
            lines.append(f"🕐 <b>{ist_time}</b>\n   {flag(h)} <b>{h}</b> vs <b>{a}</b> {flag(a)}\n   📌 {stage} | 🏟 {venue}")
        else:
            gh, ga = get_score(m)
            lines.append(f"🕐 <b>{ist_time}</b>\n   {flag(h)} <b>{h}</b> {gh}–{ga} <b>{a}</b> {flag(a)}\n   📌 {stage} | 🏟 {venue}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fixtures = get_tomorrows_fixtures()
    if not fixtures:
        await update.message.reply_text("😴 <b>No World Cup matches tomorrow</b>", parse_mode="HTML")
        return
    
    tomorrow_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%d %B %Y")
    lines = [f"📅 <b>TOMORROW'S MATCHES — {tomorrow_date}</b>\n"]
    lines.append(f"⚽ {len(fixtures)} match{'es' if len(fixtures) != 1 else ''}\n")
    
    for m in sorted(fixtures, key=lambda f: f.get("utcDate", "")):
        h     = get_home_name(m)
        a     = get_away_name(m)
        stage = m.get("stage", "").replace("_", " ").title()
        venue = m.get("venue", "") or ""
        ist_time = utc_to_ist(m["utcDate"])
        lines.append(f"🕐 <b>{ist_time}</b>\n   {flag(h)} <b>{h}</b> vs <b>{a}</b> {flag(a)}\n   📌 {stage} | 🏟 {venue}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def next_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fixtures = get_todays_fixtures()
    now_ts = int(time.time())
    
    upcoming = [m for m in fixtures if get_match_ts(m) > now_ts and m["status"] in ("TIMED","SCHEDULED")]
    
    if not upcoming:
        await update.message.reply_text("😴 <b>No upcoming matches today</b>", parse_mode="HTML")
        return
    
    next_fix = sorted(upcoming, key=lambda m: m.get("utcDate",""))[0]
    h     = get_home_name(next_fix)
    a     = get_away_name(next_fix)
    ts    = get_match_ts(next_fix)
    stage = next_fix.get("stage","").replace("_"," ").title()
    city  = next_fix.get("venue","") or ""
    
    ist_time = utc_to_ist(next_fix["utcDate"])
    time_until = ts - now_ts
    hours = time_until // 3600
    minutes = (time_until % 3600) // 60
    
    text = (
        f"⏭ <b>NEXT MATCH</b>\n\n"
        f"{flag(h)} <b>{h}</b> vs <b>{a}</b> {flag(a)}\n\n"
        f"🕐 {ist_time}\n"
        f"⏰ In {hours}h {minutes}m\n"
        f"📌 {stage}\n"
        f"🏟 {city}"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fixtures = get_finished_fixtures()
    if not fixtures:
        await update.message.reply_text("😴 <b>No finished matches today</b>", parse_mode="HTML")
        return
    
    lines = ["🏁 <b>LATEST RESULTS</b>\n"]
    
    for m in fixtures:
        h      = get_home_name(m)
        a      = get_away_name(m)
        gh, ga = get_score(m)
        lines.append(f"{flag(h)} <b>{h}</b> {gh}–{ga} <b>{a}</b> {flag(a)} ✅")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def topscorers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scorers = get_top_scorers()
    if not scorers:
        await update.message.reply_text("😴 <b>No scorer data available</b>", parse_mode="HTML")
        return
    
    lines = ["⚽ <b>GOLDEN BOOT — TOP SCORERS</b>\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, entry in enumerate(scorers[:10]):
        p      = entry.get("player", {}).get("name", "Unknown")
        team   = entry.get("team", {}).get("name", "")
        goals  = entry.get("goals", 0) or 0
        assists= entry.get("assists", 0) or 0
        medal  = medals[i] if i < len(medals) else f"{i+1}."
        lines.append(f"{medal} {flag(team)} <b>{p}</b> — ⚽{goals} 🎯{assists}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def topassists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assists = get_top_assists()
    if not assists:
        await update.message.reply_text("😴 <b>No assist data available</b>", parse_mode="HTML")
        return
    
    lines = ["🎯 <b>GOLDEN PLAYMAKER — TOP ASSISTS</b>\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, entry in enumerate(assists[:10]):
        p      = entry.get("player", {}).get("name", "Unknown")
        team   = entry.get("team", {}).get("name", "")
        ast    = entry.get("assists", 0) or 0
        goals  = entry.get("goals", 0) or 0
        medal  = medals[i] if i < len(medals) else f"{i+1}."
        lines.append(f"{medal} {flag(team)} <b>{p}</b> — 🎯{ast} ⚽{goals}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def standings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_groups = get_standings()
    if not all_groups:
        await update.message.reply_text("😴 <b>No standings data available</b>", parse_mode="HTML")
        return
    
    lines = ["🏆 <b>GROUP STANDINGS</b>\n"]
    
    for group in all_groups:
        if not group or group.get("type") != "TOTAL":
            continue
        grp_name = group.get("group","").replace("GROUP_","Group ")
        lines.append(f"\n📌 <b>{grp_name}</b>")
        for i, row in enumerate(group.get("table",[])[:4]):
            name = row["team"]["name"]
            pts  = row["points"]
            w    = row["won"]
            d    = row["draw"]
            l    = row["lost"]
            gf   = row["goalsFor"]
            ga   = row["goalsAgainst"]
            played = w + d + l
            lines.append(f"{i+1:2d}  {flag(name)} {name[:15]:15s}  {played:2d}  {w:1d}  {d:1d}  {l:1d}  {gf:2d}:{ga:2d}  {pts:3d}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /group <group_name>\nExample: /group A", parse_mode="HTML")
        return
    
    group_name = context.args[0].upper()
    all_groups = get_standings()
    
    if not all_groups:
        await update.message.reply_text("😴 <b>No standings data available</b>", parse_mode="HTML")
        return
    
    for group in all_groups:
        if not group:
            continue
        if group[0].get("group", "") == group_name:
            lines = [f"📌 <b>GROUP {group_name} STANDINGS</b>\n"]
            lines.append("Pos  Team                P  W  D  L  GF:GA  PTS")
            
            for i, team in enumerate(group):
                name = team["team"]["name"]
                pts = team["points"]
                w = team["all"]["win"]
                d = team["all"]["draw"]
                l = team["all"]["lose"]
                gf = team["all"]["goals"]["for"]
                ga = team["all"]["goals"]["against"]
                played = team["all"]["played"]
                
                lines.append(f"{i+1:2d}   {flag(name)} {name[:15]:15s}  {played:2d}  {w:1d}  {d:1d}  {l:1d}  {gf:2d}:{ga:2d}  {pts:3d}")
            
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
            return
    
    await update.message.reply_text(f"😴 <b>Group {group_name} not found</b>", parse_mode="HTML")

async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /team <team_name>\nExample: /team Brazil", parse_mode="HTML")
        return
    
    team_name = " ".join(context.args)
    team_info = get_team_info(team_name)
    
    if not team_info:
        await update.message.reply_text(f"😴 <b>Team '{team_name}' not found</b>", parse_mode="HTML")
        return
    
    team_id = team_info["team"]["id"]
    name = team_info["team"]["name"]
    country = team_info["team"]["country"]
    founded = team_info["team"].get("founded", "N/A")
    
    fixtures = get_team_fixtures(team_id)
    
    lines = [
        f"{flag(name)} <b>{name}</b>\n",
        f"🏳 Country: {country}\n",
        f"📅 Founded: {founded}\n",
        f"⚽ Matches in WC 2026: {len(fixtures)}\n"
    ]
    
    if fixtures:
        lines.append("\n📅 <b>Recent & Upcoming Matches</b>\n")
        for fix in fixtures[-5:]:
            h = fix["teams"]["home"]["name"]
            a = fix["teams"]["away"]["name"]
            gs = fix["goals"]["home"] or 0
            ga = fix["goals"]["away"] or 0
            status = fix["fixture"]["status"]["short"]
            ts = fix["fixture"]["timestamp"]
            
            if status == "NS":
                ist_time = utc_to_ist(ts)
                lines.append(f"🕐 {ist_time} — {flag(h)} {h} vs {a} {flag(a)}")
            else:
                lines.append(f"🏁 {flag(h)} {h} {gs}–{ga} {a} {flag(a)} ({status})")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def player_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /player <player_name>\nExample: /player Messi", parse_mode="HTML")
        return
    
    player_name = " ".join(context.args)
    player_info = get_player_info(player_name)
    
    if not player_info:
        await update.message.reply_text(f"😴 <b>Player '{player_name}' not found</b>", parse_mode="HTML")
        return
    
    player_id = player_info["player"]["id"]
    name = player_info["player"]["name"]
    age = player_info["player"].get("age", "N/A")
    nationality = player_info["player"]["nationality"]
    
    stats = get_player_stats(player_id)
    
    lines = [
        f"⚽ <b>{name}</b>\n",
        f"🏳 {nationality}\n",
        f"🎂 Age: {age}\n"
    ]
    
    if stats:
        team = stats["team"]["name"]
        games = stats["games"].get("appearences", 0)
        goals = stats["goals"].get("total", 0)
        assists = stats["goals"].get("assists", 0)
        yellow = stats["cards"].get("yellow", 0)
        red = stats["cards"].get("red", 0)
        
        lines.append(f"\n📊 <b>Season Statistics</b>")
        lines.append(f"🏟 Team: {flag(team)} {team}")
        lines.append(f"🎮 Appearances: {games}")
        lines.append(f"⚽ Goals: {goals}")
        lines.append(f"🎯 Assists: {assists}")
        lines.append(f"🟨 Yellow Cards: {yellow}")
        lines.append(f"🟥 Red Cards: {red}")
    else:
        lines.append("\n😴 No statistics available for this player")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def match_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /match <team1> vs <team2>\nExample: /match Brazil vs Argentina", parse_mode="HTML")
        return
    
    # Parse "team1 vs team2" format
    try:
        vs_index = context.args.index("vs")
        team1 = " ".join(context.args[:vs_index])
        team2 = " ".join(context.args[vs_index+1:])
    except ValueError:
        await update.message.reply_text("Usage: /match <team1> vs <team2>\nExample: /match Brazil vs Argentina", parse_mode="HTML")
        return
    
    fixture = get_fixture_by_teams(team1, team2)
    
    if not fixture:
        await update.message.reply_text(f"😴 <b>Match between {team1} and {team2} not found today</b>", parse_mode="HTML")
        return
    
    h = fixture["teams"]["home"]["name"]
    a = fixture["teams"]["away"]["name"]
    gs = fixture["goals"]["home"] or 0
    ga = fixture["goals"]["away"] or 0
    status = fixture["fixture"]["status"]["short"]
    ts = fixture["fixture"]["timestamp"]
    group = fixture["league"].get("round", "")
    venue = fixture["fixture"]["venue"]["name"] or ""
    city = fixture["fixture"]["venue"]["city"] or ""
    
    ist_time = utc_to_ist(ts)
    
    lines = [
        f"{flag(h)} <b>{h}</b> {gs}–{ga} <b>{a}</b> {flag(a)}\n",
        f"📌 {group}\n",
        f"🏟 {venue}, {city}\n",
        f"🕐 {ist_time}\n",
        f"📊 Status: {status}"
    ]
    
    if status in ("1H", "2H", "HT", "ET"):
        elapsed = fixture["fixture"]["status"].get("elapsed", 0)
        lines.append(f"⏱ {elapsed}'")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["📊 <b>TOURNAMENT STATISTICS</b>\n"]
    
    scorers = get_top_scorers()
    if scorers:
        total_goals = sum(s["statistics"][0]["goals"]["total"] or 0 for s in scorers[:20])
        lines.append(f"⚽ Total Goals (Top 20): {total_goals}")
    
    all_groups = get_standings()
    if all_groups:
        total_teams = sum(len(g) for g in all_groups if g)
        lines.append(f"🏆 Teams: {total_teams}")
    
    fixtures = get_todays_fixtures()
    if fixtures:
        lines.append(f"📅 Matches Today: {len(fixtures)}")
    
    live = get_live_fixtures()
    lines.append(f"🔴 Live Matches: {len(live)}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

# ─── STATS DASHBOARD ───────────────────────────────────────────────────────────
def send_daily_fixtures(state: dict) -> dict:
    """Send today's full fixture list at 08:00 IST."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"daily_fixtures_{today}"
    if key in state:
        return state

    fixtures = get_todays_fixtures()
    if not fixtures:
        state[key] = True
        send(f"😴 <b>No World Cup matches today</b> ({today})\nEnjoy the rest day! Next matches coming soon. 🏆")
        return state

    lines = [f"📅 <b>TODAY'S MATCHES — {datetime.now(timezone.utc).strftime('%d %B %Y')}</b>"]
    lines.append(f"⚽ {len(fixtures)} match{'es' if len(fixtures) != 1 else ''} today\n")

    for fix in sorted(fixtures, key=lambda f: f["fixture"]["timestamp"]):
        h = fix["teams"]["home"]["name"]
        a = fix["teams"]["away"]["name"]
        ts = fix["fixture"]["timestamp"]
        group = fix["league"].get("round", "")
        venue = fix["fixture"]["venue"]["name"] or ""
        city = fix["fixture"]["venue"]["city"] or ""

        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        utc_str = dt_utc.strftime("%H:%M UTC")
        ist_time = utc_to_ist(ts)

        lines.append(
            f"🕐 <b>{utc_str}</b>  ({ist_time})\n"
            f"   {flag(h)} <b>{h}</b>  vs  <b>{a}</b> {flag(a)}\n"
            f"   📌 {group}  |  🏟 {city}"
        )

    lines.append("\n🔔 You'll get alerts 15 min before each kick-off!")
    send("\n".join(lines))
    state[key] = True
    return state

def send_daily_stats(state: dict) -> dict:
    """Send a full stats snapshot: top scorers, assists, best teams."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"daily_stats_{today}"
    if key in state:
        return state

    lines = ["📊 <b>WORLD CUP 2026 — DAILY STATS UPDATE</b>"]
    lines.append(f"📅 {datetime.now(timezone.utc).strftime('%d %B %Y')}\n")

    scorers = get_top_scorers()
    if scorers:
        lines.append("⚽ <b>TOP SCORERS — Golden Boot race</b>")
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, entry in enumerate(scorers[:5]):
            p = entry["player"]["name"]
            team = entry["statistics"][0]["team"]["name"]
            goals = entry["statistics"][0]["goals"]["total"] or 0
            assists = entry["statistics"][0]["goals"]["assists"] or 0
            medal = medals[i] if i < len(medals) else f"{i+1}."
            lines.append(f"{medal} {flag(team)} <b>{p}</b>  ⚽ {goals}  🎯 {assists} ast")
        lines.append("")

    assists_list = get_top_assists()
    if assists_list:
        lines.append("🎯 <b>TOP ASSISTS — Golden Playmaker</b>")
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, entry in enumerate(assists_list[:5]):
            p = entry["player"]["name"]
            team = entry["statistics"][0]["team"]["name"]
            ast = entry["statistics"][0]["goals"]["assists"] or 0
            goals = entry["statistics"][0]["goals"]["total"] or 0
            medal = medals[i] if i < len(medals) else f"{i+1}."
            lines.append(f"{medal} {flag(team)} <b>{p}</b>  🎯 {ast}  ⚽ {goals} goals")
        lines.append("")

    all_groups = get_standings()
    if all_groups:
        lines.append("🏆 <b>GROUP LEADERS</b>")
        for group in all_groups:
            if not group:
                continue
            leader = group[0]
            team = leader["team"]["name"]
            pts = leader["points"]
            w = leader["all"]["win"]
            d = leader["all"]["draw"]
            l = leader["all"]["lose"]
            gf = leader["all"]["goals"]["for"]
            ga_t = leader["all"]["goals"]["against"]
            grp_name = leader.get("group", "")
            lines.append(
                f"  {flag(team)} <b>{team}</b> ({grp_name}) — "
                f"{pts}pts  W{w} D{d} L{l}  {gf}:{ga_t}"
            )
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("🔔 Live alerts continue all day. Stay tuned! ⚽")

    send("\n".join(lines))
    state[key] = True
    return state

def send_match_stats(fix: dict):
    """After full time, send mini stats for that match."""
    fid = fix["fixture"]["id"]
    h = fix["teams"]["home"]
    a = fix["teams"]["away"]
    gh = fix["goals"]["home"] or 0
    ga = fix["goals"]["away"] or 0

    data = api_get("/fixtures/players", {"fixture": fid})
    teams = data.get("response", [])

    lines = [f"📈 <b>MATCH STATS</b>  {flag(h['name'])} {h['name']} {gh}–{ga} {a['name']} {flag(a['name'])}"]

    for team_data in teams:
        tname = team_data["team"]["name"]
        players = team_data["players"]
        rated = sorted(
            [p for p in players if p["statistics"][0].get("games", {}).get("rating")],
            key=lambda p: float(p["statistics"][0]["games"]["rating"] or 0),
            reverse=True
        )
        if rated:
            top = rated[0]
            pname = top["player"]["name"]
            rating = float(top["statistics"][0]["games"]["rating"])
            goals = top["statistics"][0]["goals"].get("total") or 0
            assists = top["statistics"][0]["goals"].get("assists") or 0
            lines.append(
                f"  ⭐ {flag(tname)} <b>{pname}</b> ({tname})  "
                f"Rating {rating:.1f}  ⚽{goals}  🎯{assists}"
            )

    send("\n".join(lines))

def process_fixture(m: dict, state: dict) -> dict:
    """Process a football-data.org match object for live notifications."""
    mid    = str(m["id"])
    status = m["status"]   # IN_PLAY, PAUSED, FINISHED

    if mid not in state:
        state[mid] = {"sent_start": False, "sent_ht": False, "sent_ft": False, "goals_seen": []}

    ms     = state[mid]
    header = match_header(m)
    venue  = m.get("venue", "") or ""
    stage  = m.get("stage", "").replace("_", " ").title()

    # Kick-off
    if status == "IN_PLAY" and not ms["sent_start"]:
        ms["sent_start"] = True
        utcdt = m.get("utcDate", "")
        send(f"🟢 <b>KICK-OFF!</b>\n{header}\n🏟 {venue}  |  📌 {stage}\n🕐 {utc_to_ist(utcdt)}")

    # Half time
    if status == "PAUSED" and not ms["sent_ht"]:
        ms["sent_ht"] = True
        send(f"🔶 <b>HALF TIME</b>\n{header}")

    # Goals
    goals = api_get(f"/matches/{m['id']}").get("goals", [])
    for g in goals:
        scorer  = (g.get("scorer") or {}).get("name", "Unknown")
        team    = (g.get("team") or {}).get("name", "")
        minute  = g.get("minute", 0)
        g_type  = g.get("type", "")
        g_id    = f"{minute}_{scorer}"

        if g_id in ms["goals_seen"]:
            continue
        ms["goals_seen"].append(g_id)

        if g_type == "OWN_GOAL":
            send(f"😬 <b>OWN GOAL!</b>  {minute}'\n{header}\n😬 {scorer} ({flag(team)} {team})")
        elif g_type == "PENALTY":
            send(f"🎯 <b>PENALTY GOAL!</b>  {minute}'\n{header}\n🎯 {scorer} ({flag(team)} {team})")
        else:
            send(f"⚽ <b>GOAL!</b>  {minute}'\n{header}\n👟 {scorer} ({flag(team)} {team})")

    # Full time
    if status == "FINISHED" and not ms["sent_ft"]:
        ms["sent_ft"] = True
        h  = get_home_name(m)
        a  = get_away_name(m)
        gh, ga = get_score(m)
        if gh > ga:   winner = f"🏆 <b>{h}</b> wins!"
        elif ga > gh: winner = f"🏆 <b>{a}</b> wins!"
        else:         winner = "🤝 It's a <b>draw</b>!"
        send(f"🏁 <b>FULL TIME</b>\n{header}\n{winner}")

    return state

def check_upcoming(state: dict) -> dict:
    now_ts   = int(time.time())
    for m in get_todays_fixtures():
        mid    = str(m["id"])
        status = m["status"]
        if status not in ("TIMED", "SCHEDULED"):
            continue
        ts   = get_match_ts(m)
        diff = ts - now_ts
        key  = f"reminder_{mid}"
        if 0 < diff <= 900 and key not in state:
            state[key] = True
            h     = get_home_name(m)
            a     = get_away_name(m)
            stage = m.get("stage", "").replace("_", " ").title()
            send(
                f"⏰ <b>MATCH IN ~15 MIN!</b>\n"
                f"{flag(h)} {h}  vs  {a} {flag(a)}\n"
                f"🕐 {utc_to_ist(m['utcDate'])}\n"
                f"📌 {stage}"
            )
    return state

def should_send_daily_stats() -> bool:
    """Send daily stats at 08:00 IST (02:30 UTC)."""
    now_utc = datetime.now(timezone.utc)
    return now_utc.hour == 2 and now_utc.minute < 3

# ─── BACKGROUND NOTIFICATION LOOP ───────────────────────────────────────────────
def notification_loop():
    """Run the notification loop in a separate thread."""
    print("🔔 Notification loop started!")
    send(
        "🤖 <b>World Cup 2026 Bot is ON!</b>\n\n"
        "You'll receive:\n"
        "⏰ 15-min match reminders\n"
        "🟢 Kick-off alerts\n"
        "⚽ Live goals (scorer + minute)\n"
        "🟨🟥 Card alerts\n"
        "🔶 Half-time scores\n"
        "🏁 Full-time results\n"
        "📈 Post-match player ratings\n"
        "📊 Daily stats (top scorers, assists, group leaders)\n\n"
        "Use /help to see interactive commands. All 104 matches covered. Let's go! 🏆"
    )

    state = load_state()

    while True:
        try:
            if should_send_daily_stats():
                state = send_daily_fixtures(state)
                state = send_daily_stats(state)
                save_state(state)

            state = check_upcoming(state)

            live = get_live_fixtures()
            if live:
                for m in live:
                    state = process_fixture(m, state)
                save_state(state)
                time.sleep(POLL_INTERVAL_LIVE)
            else:
                save_state(state)
                time.sleep(POLL_INTERVAL_IDLE)

        except KeyboardInterrupt:
            print("Notification loop stopped.")
            break
        except Exception as e:
            print(f"[Notification Error] {e}")
            time.sleep(60)

# ─── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    print("🤖 World Cup 2026 Bot started!")
    
    # Start notification loop in background thread
    notification_thread = threading.Thread(target=notification_loop, daemon=True)
    notification_thread.start()
    
    # Create Telegram application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("live", live))
    application.add_handler(CommandHandler("today", today))
    application.add_handler(CommandHandler("tomorrow", tomorrow))
    application.add_handler(CommandHandler("next", next_match))
    application.add_handler(CommandHandler("results", results))
    application.add_handler(CommandHandler("topscorers", topscorers))
    application.add_handler(CommandHandler("topassists", topassists))
    application.add_handler(CommandHandler("standings", standings))
    application.add_handler(CommandHandler("group", group_command))
    application.add_handler(CommandHandler("team", team_command))
    application.add_handler(CommandHandler("player", player_command))
    application.add_handler(CommandHandler("match", match_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
