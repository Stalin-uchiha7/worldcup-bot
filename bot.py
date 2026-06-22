import os
import time
import requests
import json
from datetime import datetime, timezone

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
API_KEY        = os.environ.get("FOOTBALL_API_KEY")

HEADERS  = {"x-apisports-key": API_KEY}
BASE_URL = "https://v3.football.api-sports.io"

WC2026_LEAGUE = 1
WC2026_SEASON = 2026

POLL_INTERVAL_LIVE = 30
POLL_INTERVAL_IDLE = 120

STATE_FILE = "state.json"

# ─── TELEGRAM ──────────────────────────────────────────────────────────────────
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

def match_header(fix: dict) -> str:
    h  = fix["teams"]["home"]
    a  = fix["teams"]["away"]
    gs = fix["goals"]["home"] if fix["goals"]["home"] is not None else 0
    ga = fix["goals"]["away"] if fix["goals"]["away"] is not None else 0
    return f"{flag(h['name'])} <b>{h['name']}</b> {gs} – {ga} <b>{a['name']}</b> {flag(a['name'])}"

# ─── API CALLS ─────────────────────────────────────────────────────────────────
def api_get(path: str, params: dict) -> dict:
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=15)
        return r.json()
    except Exception as e:
        print(f"[API error] {e}")
        return {}

def get_live_fixtures() -> list:
    return api_get("/fixtures", {"live": "all", "league": WC2026_LEAGUE, "season": WC2026_SEASON}).get("response", [])

def get_todays_fixtures() -> list:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return api_get("/fixtures", {"league": WC2026_LEAGUE, "season": WC2026_SEASON, "date": today}).get("response", [])

def get_fixture_events(fixture_id: int) -> list:
    return api_get("/fixtures/events", {"fixture": fixture_id}).get("response", [])

def get_top_scorers() -> list:
    return api_get("/players/topscorers", {"league": WC2026_LEAGUE, "season": WC2026_SEASON}).get("response", [])

def get_top_assists() -> list:
    return api_get("/players/topassists", {"league": WC2026_LEAGUE, "season": WC2026_SEASON}).get("response", [])

def get_standings() -> list:
    data = api_get("/standings", {"league": WC2026_LEAGUE, "season": WC2026_SEASON})
    try:
        return data["response"][0]["league"]["standings"]
    except Exception:
        return []

# ─── STATS DASHBOARD ───────────────────────────────────────────────────────────
def send_daily_fixtures(state: dict) -> dict:
    """Send today's full fixture list at 08:00 IST."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key   = f"daily_fixtures_{today}"
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
        h      = fix["teams"]["home"]["name"]
        a      = fix["teams"]["away"]["name"]
        ts     = fix["fixture"]["timestamp"]
        group  = fix["league"].get("round", "")
        venue  = fix["fixture"]["venue"]["name"] or ""
        city   = fix["fixture"]["venue"]["city"] or ""

        # Times
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        utc_str = dt_utc.strftime("%H:%M UTC")

        # IST = UTC + 5:30
        total_minutes = dt_utc.hour * 60 + dt_utc.minute + 330
        ist_h = (total_minutes // 60) % 24
        ist_m = total_minutes % 60
        ist_str = f"{ist_h:02d}:{ist_m:02d} IST"

        lines.append(
            f"🕐 <b>{utc_str}</b>  ({ist_str})\n"
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
    key   = f"daily_stats_{today}"
    if key in state:
        return state   # already sent today

    lines = ["📊 <b>WORLD CUP 2026 — DAILY STATS UPDATE</b>"]
    lines.append(f"📅 {datetime.now(timezone.utc).strftime('%d %B %Y')}\n")

    # ── TOP SCORERS ──────────────────────────────────────────────────────────
    scorers = get_top_scorers()
    if scorers:
        lines.append("⚽ <b>TOP SCORERS — Golden Boot race</b>")
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, entry in enumerate(scorers[:5]):
            p      = entry["player"]["name"]
            team   = entry["statistics"][0]["team"]["name"]
            goals  = entry["statistics"][0]["goals"]["total"] or 0
            assists= entry["statistics"][0]["goals"]["assists"] or 0
            medal  = medals[i] if i < len(medals) else f"{i+1}."
            lines.append(f"{medal} {flag(team)} <b>{p}</b>  ⚽ {goals}  🎯 {assists} ast")
        lines.append("")

    # ── TOP ASSISTS ──────────────────────────────────────────────────────────
    assists_list = get_top_assists()
    if assists_list:
        lines.append("🎯 <b>TOP ASSISTS — Golden Playmaker</b>")
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, entry in enumerate(assists_list[:5]):
            p      = entry["player"]["name"]
            team   = entry["statistics"][0]["team"]["name"]
            ast    = entry["statistics"][0]["goals"]["assists"] or 0
            goals  = entry["statistics"][0]["goals"]["total"] or 0
            medal  = medals[i] if i < len(medals) else f"{i+1}."
            lines.append(f"{medal} {flag(team)} <b>{p}</b>  🎯 {ast}  ⚽ {goals} goals")
        lines.append("")

    # ── BEST TEAMS (group leaders by points) ────────────────────────────────
    all_groups = get_standings()
    if all_groups:
        lines.append("🏆 <b>GROUP LEADERS</b>")
        for group in all_groups:
            if not group:
                continue
            leader = group[0]
            team   = leader["team"]["name"]
            pts    = leader["points"]
            w      = leader["all"]["win"]
            d      = leader["all"]["draw"]
            l      = leader["all"]["lose"]
            gf     = leader["all"]["goals"]["for"]
            ga_t   = leader["all"]["goals"]["against"]
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

# ─── MATCH-END STATS SNAPSHOT ──────────────────────────────────────────────────
def send_match_stats(fix: dict):
    """After full time, send mini stats for that match."""
    fid = fix["fixture"]["id"]
    h   = fix["teams"]["home"]
    a   = fix["teams"]["away"]
    gh  = fix["goals"]["home"] or 0
    ga  = fix["goals"]["away"] or 0

    # Fetch player stats for this fixture
    data   = api_get("/fixtures/players", {"fixture": fid})
    teams  = data.get("response", [])

    lines = [f"📈 <b>MATCH STATS</b>  {flag(h['name'])} {h['name']} {gh}–{ga} {a['name']} {flag(a['name'])}"]

    for team_data in teams:
        tname   = team_data["team"]["name"]
        players = team_data["players"]
        # top rated player
        rated = sorted(
            [p for p in players if p["statistics"][0].get("games", {}).get("rating")],
            key=lambda p: float(p["statistics"][0]["games"]["rating"] or 0),
            reverse=True
        )
        if rated:
            top    = rated[0]
            pname  = top["player"]["name"]
            rating = float(top["statistics"][0]["games"]["rating"])
            goals  = top["statistics"][0]["goals"].get("total") or 0
            assists= top["statistics"][0]["goals"].get("assists") or 0
            lines.append(
                f"  ⭐ {flag(tname)} <b>{pname}</b> ({tname})  "
                f"Rating {rating:.1f}  ⚽{goals}  🎯{assists}"
            )

    send("\n".join(lines))

# ─── NOTIFICATION LOGIC ────────────────────────────────────────────────────────
def process_fixture(fix: dict, state: dict) -> dict:
    fid    = fix["fixture"]["id"]
    fkey   = str(fid)
    status = fix["fixture"]["status"]["short"]

    if fkey not in state:
        state[fkey] = {"sent_start": False, "sent_ht": False, "sent_ft": False, "events_seen": []}

    fs     = state[fkey]
    header = match_header(fix)
    venue  = fix["fixture"]["venue"]["name"] or ""

    # ── KICK-OFF ─────────────────────────────────────────────────────────────
    if status in ("1H", "2H", "ET") and not fs["sent_start"]:
        fs["sent_start"] = True
        group = fix["league"].get("round", "")
        send(f"🟢 <b>KICK-OFF!</b>\n{header}\n🏟 {venue}\n📌 {group}")

    # ── HALF TIME ────────────────────────────────────────────────────────────
    if status == "HT" and not fs["sent_ht"]:
        fs["sent_ht"] = True
        send(f"🔶 <b>HALF TIME</b>\n{header}")

    # ── EVENTS ───────────────────────────────────────────────────────────────
    events = get_fixture_events(fid)
    for ev in events:
        ev_id = f"{ev['time']['elapsed']}_{ev['type']}_{ev['player']['name']}"
        if ev_id in fs["events_seen"]:
            continue
        fs["events_seen"].append(ev_id)

        etype  = ev["type"]
        detail = ev["detail"]
        player = ev["player"]["name"] or "Unknown"
        team   = ev["team"]["name"]
        t      = ev["time"]["elapsed"]
        extra  = ev["time"].get("extra")
        min_s  = f"{t}+{extra}'" if extra else f"{t}'"

        if etype == "Goal":
            emoji = "😬 <b>OWN GOAL!</b>" if detail == "Own Goal" else "🎯 <b>PENALTY GOAL!</b>" if detail == "Penalty" else "⚽ <b>GOAL!</b>"
            icon  = "😬" if detail == "Own Goal" else "🎯" if detail == "Penalty" else "👟"
            send(f"{emoji}  {min_s}\n{header}\n{icon} {player} ({flag(team)} {team})")

        elif etype == "Card":
            if detail == "Yellow Card":
                send(f"🟨 <b>YELLOW CARD</b>  {min_s}\n{header}\n🚶 {player} ({flag(team)} {team})")
            elif detail in ("Red Card", "Yellow Red Card", "Second Yellow card"):
                send(f"🟥 <b>RED CARD!</b>  {min_s}\n{header}\n🚨 {player} ({flag(team)} {team})")

    # ── FULL TIME ────────────────────────────────────────────────────────────
    if status in ("FT", "AET", "PEN") and not fs["sent_ft"]:
        fs["sent_ft"] = True
        h  = fix["teams"]["home"]
        a  = fix["teams"]["away"]
        gh = fix["goals"]["home"] or 0
        ga = fix["goals"]["away"] or 0

        if gh > ga:   winner = f"🏆 <b>{h['name']}</b> wins!"
        elif ga > gh: winner = f"🏆 <b>{a['name']}</b> wins!"
        else:         winner = "🤝 It's a <b>draw</b>!"

        suffix = " (AET)" if status == "AET" else " (Pens)" if status == "PEN" else ""
        send(f"🏁 <b>FULL TIME{suffix}</b>\n{header}\n{winner}\n📊 Final: {h['name']} {gh}–{ga} {a['name']}")

        # ── POST-MATCH PLAYER STATS ─────────────────────────────────────────
        send_match_stats(fix)

    return state

# ─── UPCOMING ALERTS ───────────────────────────────────────────────────────────
def check_upcoming(state: dict) -> dict:
    now_ts   = int(time.time())
    fixtures = get_todays_fixtures()
    for fix in fixtures:
        fid    = str(fix["fixture"]["id"])
        ts     = fix["fixture"]["timestamp"]
        diff   = ts - now_ts
        status = fix["fixture"]["status"]["short"]
        if status != "NS":
            continue
        key = f"reminder_{fid}"
        if 0 < diff <= 900 and key not in state:
            state[key] = True
            h   = fix["teams"]["home"]["name"]
            a   = fix["teams"]["away"]["name"]
            kof = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M UTC")
            # Convert to IST (UTC+5:30)
            ist_h = (datetime.fromtimestamp(ts, tz=timezone.utc).hour + 5) % 24
            ist_m = (datetime.fromtimestamp(ts, tz=timezone.utc).minute + 30) % 60
            ist_h = ist_h + 1 if (datetime.fromtimestamp(ts, tz=timezone.utc).minute + 30) >= 60 else ist_h
            group = fix["league"].get("round", "")
            send(
                f"⏰ <b>MATCH IN ~15 MIN!</b>\n"
                f"{flag(h)} {h}  vs  {a} {flag(a)}\n"
                f"🕐 {kof}  ({ist_h:02d}:{ist_m:02d} IST)\n"
                f"📌 {group}"
            )
    return state

# ─── DAILY STATS SCHEDULER ─────────────────────────────────────────────────────
def should_send_daily_stats() -> bool:
    """Send daily stats at 08:00 IST (02:30 UTC)."""
    now_utc = datetime.now(timezone.utc)
    return now_utc.hour == 2 and now_utc.minute < 3   # 2-min window

# ─── MAIN LOOP ─────────────────────────────────────────────────────────────────
def main():
    print("🤖 World Cup 2026 Bot started!")
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
        "All 104 matches covered. Let's go! 🏆"
    )

    state = load_state()

    while True:
        try:
            # Daily fixtures + stats at 08:00 IST
            if should_send_daily_stats():
                state = send_daily_fixtures(state)
                state = send_daily_stats(state)
                save_state(state)

            # 15-min reminders
            state = check_upcoming(state)

            # Live match processing
            live = get_live_fixtures()
            if live:
                for fix in live:
                    state = process_fixture(fix, state)
                save_state(state)
                time.sleep(POLL_INTERVAL_LIVE)
            else:
                save_state(state)
                time.sleep(POLL_INTERVAL_IDLE)

        except KeyboardInterrupt:
            print("Bot stopped.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
