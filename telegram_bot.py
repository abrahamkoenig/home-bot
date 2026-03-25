#!/usr/bin/env python3
"""Personal AI home assistant on Telegram — controls Philips Hue lights,
monitors network, posts to LinkedIn, checks emails, manages calendar and reminders.
Powered by Claude API."""
import os, sys, subprocess, json, hashlib, urllib.request, urllib.parse, re, datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

# --- Configuration (set these before running) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "your-telegram-bot-token")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "your-claude-api-key")
HUE_SCRIPT = os.path.expanduser("~/hue.py")
HUE_IP = os.environ.get("HUE_IP", "192.168.x.x")
HUE_API_KEY = os.environ.get("HUE_API_KEY", "your-hue-api-key")

# LinkedIn config
LINKEDIN_TOKEN_FILE = os.path.expanduser("~/.linkedin_token.json")

# Email config (IMAP)
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.mail.me.com")
IMAP_USER = os.environ.get("IMAP_USER", "your-email@icloud.com")
IMAP_PASS = os.environ.get("IMAP_PASS", "")

# FRITZ!Box config
FRITZ_IP = os.environ.get("FRITZ_IP", "192.168.178.1")
FRITZ_USER = os.environ.get("FRITZ_USER", "your-fritz-user")
FRITZ_PASS = os.environ.get("FRITZ_PASS", "your-fritz-password")

# Reminders helper (compiled Swift binary using EventKit)
REMINDERS_HELPER = os.path.expanduser("~/reminders_helper")

# Only allow your own Telegram user ID (set after first /start)
ALLOWED_USERS = set()
ADMIN_FILE = os.path.expanduser("~/.telegram_bot_admins.json")

# Conversation history per user
conversations = {}

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)


def get_system_prompt():
    today = datetime.date.today().isoformat()
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday = weekdays[datetime.date.today().weekday()]
    return f"""You are a personal home assistant on Telegram. You respond concisely and helpfully.

Today is {weekday}, {today}.

You can control Hue lights with these commands:
- alles-aus: All lights off (saves state first)
- alles-an: All lights on
- wiederherstellen: Restore previous light state
- gute-nacht: All off, bedroom nightlight on
- guten-morgen: Bedroom, kitchen, bathroom bright
- filmabend: Living room dimmed
- kochen: Kitchen bright
- arbeiten: Office work light
- garten-an / garten-aus: Garden on/off
- entspannen: Living room warm dimmed
- status: Show which rooms are on/off
- [room] an/aus/toggle: Control individual room

You can check the network/WLAN:
- netzwerk-geräte: Show all connected devices
- netzwerk-scan: Quick ARP network scan
- netzwerk-info: Internet connection info

You can post to LinkedIn:
- When the user wants to post, publish the text.
- You can help improve the text before posting.

You can draft LinkedIn comments:
- When the user shares a LinkedIn post and wants a comment, write one.
- Comments should be short (2-4 sentences), professional but authentic.
- Add a unique perspective, not just "Great post!".

You can check emails:
- Use [MAIL:count] to fetch unread emails.

You can manage calendar and reminders:
- View events: Shows today's or upcoming events
- Create event: Add a new calendar event
- Delete event: Remove a calendar event
- Modify event: Change date, time or duration of an event
- View reminders: Shows open reminders
- Create reminder: Add a new reminder
- Complete reminder: Mark a reminder as done

Respond with [HUE:command] for light commands, e.g. [HUE:alles-aus] or [HUE:wohnzimmer an].
Respond with [NET:command] for network commands:
- [NET:geräte] for connected devices
- [NET:scan] for a network scan
- [NET:info] for connection info
Respond with [LINKEDIN:text] to post to LinkedIn.
Respond with [MAIL:count] to fetch emails, e.g. [MAIL:5].

Respond with [CAL:days:offset] or [CAL-DATE:YYYY-MM-DD] to view events.
- [CAL:1] for today (only upcoming events), [CAL:1:1] for tomorrow, [CAL:7] for the next week
- [CAL-DATE:2026-03-20] for a specific date — use this for "What was on...", "What did I have on..."
Respond with [CAL-NEW:title|date|time|duration|location] to create an event. Date YYYY-MM-DD, time HH:MM, duration in minutes. Location optional. E.g. [CAL-NEW:Meeting with Lisa|2026-03-25|15:00|60|Office].
Respond with [CAL-DEL:name|date] to delete an event. Date optional (YYYY-MM-DD). E.g. [CAL-DEL:Coffee|2026-03-25].
Respond with [CAL-MOD:name|original_date|new_date|new_time|new_duration] to modify an event. Empty fields mean no change. E.g. [CAL-MOD:Coffee|2026-03-25||10:00|] to change time to 10:00.
Respond with [REM:list] to view reminders, e.g. [REM:] for all or [REM:Shopping] for a specific list.
Respond with [REM-NEW:title|due_date|list] to create a reminder. Date optional (YYYY-MM-DD), list optional. E.g. [REM-NEW:Buy milk|2026-03-25|Shopping].
Respond with [REM-DONE:name] to mark a reminder as complete, e.g. [REM-DONE:Buy milk]."""


def load_admins():
    if os.path.exists(ADMIN_FILE):
        with open(ADMIN_FILE) as f:
            ALLOWED_USERS.update(json.load(f))

def save_admins():
    with open(ADMIN_FILE, "w") as f:
        json.dump(list(ALLOWED_USERS), f)


def run_hue(command: str) -> str:
    """Run a hue.py command and return the output."""
    parts = command.strip().split()
    try:
        result = subprocess.run(
            [sys.executable, HUE_SCRIPT] + parts,
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip() or result.stderr.strip() or "OK"
    except Exception as e:
        return f"Error: {e}"


def fritz_sid():
    """Get a session ID from FRITZ!Box."""
    url = f"http://{FRITZ_IP}/login_sid.lua"
    r = urllib.request.urlopen(url, timeout=5).read().decode()
    challenge = re.search(r"<Challenge>(.*?)</Challenge>", r).group(1)
    response = challenge + "-" + FRITZ_PASS
    response = response.encode("utf-16le")
    md5 = hashlib.md5(response).hexdigest()
    login_response = challenge + "-" + md5
    data = urllib.parse.urlencode({"username": FRITZ_USER, "response": login_response}).encode()
    r = urllib.request.urlopen(url, data, timeout=5).read().decode()
    sid = re.search(r"<SID>(.*?)</SID>", r).group(1)
    if sid == "0000000000000000":
        return None
    return sid


def fritz_request(page, params=None):
    """Make an authenticated request to FRITZ!Box."""
    sid = fritz_sid()
    if not sid:
        return None
    data = {"sid": sid, "page": page}
    if params:
        data.update(params)
    post_data = urllib.parse.urlencode(data).encode()
    url = f"http://{FRITZ_IP}/data.lua"
    req = urllib.request.Request(url, post_data)
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())


def get_network_devices() -> str:
    """Get list of connected devices from FRITZ!Box."""
    try:
        data = fritz_request("meshList")
        if not data:
            return "Error: No connection to FRITZ!Box"

        devices = data.get("data", {}).get("net", {}).get("devices", [])
        online = []
        offline = []
        for dev in devices:
            name = dev.get("name", "Unknown")
            dtype = dev.get("type", "?")
            desc = dev.get("desc", "")
            is_online = dev.get("stateinfo", {}).get("online", False)
            line = f"  {name:<28} {dtype:<5} {desc}"
            if is_online:
                online.append(line)
            else:
                offline.append(line)

        result = f"Online ({len(online)}):\n" + "\n".join(online)
        if offline:
            result += f"\n\nOffline ({len(offline)}):\n" + "\n".join(offline)
        return result
    except Exception as e:
        return f"Error: {e}"


def get_connection_info() -> str:
    """Get internet connection info from FRITZ!Box."""
    try:
        data = fritz_request("meshList")
        if not data:
            return "Error: No connection to FRITZ!Box"

        d = data.get("data", {})
        internet = d.get("internet", {})
        wlan = d.get("wlan", [])
        guest = d.get("wlan_guest", {})
        lan = d.get("lan", {})

        result = f"Internet: {internet.get('txt', '?')}\n"
        if wlan:
            result += f"WLAN: {wlan[0].get('txt', '?')}\n"
        result += f"Guest WLAN: {guest.get('txt', '?')}\n"
        result += f"LAN: {lan.get('txt', '?')}"
        return result
    except Exception as e:
        return f"Error: {e}"


def scan_network() -> str:
    """Quick network scan using arp."""
    try:
        result = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split("\n")
        devices = [line.strip() for line in lines if "192.168." in line]
        return f"Devices on network ({len(devices)}):\n" + "\n".join(devices)
    except Exception as e:
        return f"Error: {e}"


def linkedin_post(text: str) -> str:
    """Post text to LinkedIn."""
    try:
        import base64
        if not os.path.exists(LINKEDIN_TOKEN_FILE):
            return "Error: No LinkedIn token found"
        with open(LINKEDIN_TOKEN_FILE) as f:
            token_data = json.load(f)
        access_token = token_data["access_token"]

        # Get user ID from JWT id_token
        id_token = token_data.get("id_token", "")
        payload = id_token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload).decode())
        person_id = decoded["sub"]

        # Create post
        post_data = json.dumps({
            "author": f"urn:li:person:{person_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }).encode()

        req = urllib.request.Request("https://api.linkedin.com/v2/ugcPosts", post_data)
        req.add_header("Authorization", f"Bearer {access_token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Restli-Protocol-Version", "2.0.0")
        urllib.request.urlopen(req, timeout=15)
        return "LinkedIn post published!"
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return f"LinkedIn error {e.code}: {body[:200]}"
    except Exception as e:
        return f"Error: {e}"


def get_unread_emails(limit=10) -> str:
    """Get unread emails via IMAP."""
    import imaplib, email
    from email.header import decode_header
    try:
        if not IMAP_PASS:
            return "Email not configured (app-specific password missing)."
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("INBOX", readonly=True)
        _, data = mail.search(None, "UNSEEN")
        msg_ids = data[0].split() if data and data[0] else []
        if not msg_ids:
            mail.logout()
            return "No unread emails."
        total = len(msg_ids)
        # Fetch most recent ones
        recent_ids = msg_ids[-limit:]
        lines = []
        for mid in reversed(recent_ids):
            _, msg_data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            sender = msg.get("From", "?")
            subj_raw = msg.get("Subject", "?")
            decoded_parts = decode_header(subj_raw)
            subject = ""
            for part, enc in decoded_parts:
                if isinstance(part, bytes):
                    subject += part.decode(enc or "utf-8", errors="replace")
                else:
                    subject += part
            date = msg.get("Date", "?")
            if "," in date:
                date = date.split(",")[1].strip()[:20]
            lines.append(f"FROM: {sender}\nSUBJECT: {subject}\nDATE: {date}\n---")
        mail.logout()
        result = "\n".join(lines)
        result += f"\nTOTAL: {total} unread emails"
        return result
    except Exception as e:
        return f"Error fetching emails: {e}"


def get_calendar_events(days=1, offset=0) -> str:
    """Get calendar events via sqlite3. offset=0 means starting today, offset=1 means starting tomorrow."""
    try:
        db = os.path.expanduser("~/Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb")
        query = f"""
SELECT ci.summary || '|' ||
       strftime('%Y-%m-%d %H:%M', ci.start_date + 978307200, 'unixepoch', 'localtime') || '|' ||
       strftime('%H:%M', ci.end_date + 978307200, 'unixepoch', 'localtime') || '|' ||
       c.title || '|' ||
       COALESCE(l.title, '')
FROM CalendarItem ci
JOIN Calendar c ON ci.calendar_id = c.ROWID
LEFT JOIN Location l ON ci.location_id = l.ROWID
WHERE date(ci.start_date + 978307200, 'unixepoch', 'localtime') >= date('now', 'localtime', '+{offset} days')
  AND date(ci.start_date + 978307200, 'unixepoch', 'localtime') < date('now', 'localtime', '+{offset + days} days')
  AND ({offset} != 0 OR datetime(ci.end_date + 978307200, 'unixepoch', 'localtime') > datetime('now', 'localtime'))
  AND c.flags NOT IN (2, 4, 5, 519)
ORDER BY ci.start_date;"""
        result = subprocess.run(
            ["sqlite3", db, query],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        output = result.stdout.strip()
        if not output:
            if offset == 0 and days == 1:
                return "No more events for today."
            elif offset == 1 and days == 1:
                return "No events tomorrow."
            else:
                return f"No events in the next {days} days."
        lines = []
        for row in output.split("\n"):
            parts = row.split("|")
            if len(parts) >= 4:
                summary, start, end = parts[0], parts[1], parts[2]
                lines.append(f"{start}-{end} {summary}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching calendar: {e}"


def get_calendar_by_date(date_str) -> str:
    """Get calendar events for a specific date via sqlite3."""
    try:
        db = os.path.expanduser("~/Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb")
        query = f"""
SELECT ci.summary || '|' ||
       strftime('%H:%M', ci.start_date + 978307200, 'unixepoch', 'localtime') || '|' ||
       strftime('%H:%M', ci.end_date + 978307200, 'unixepoch', 'localtime')
FROM CalendarItem ci
JOIN Calendar c ON ci.calendar_id = c.ROWID
WHERE date(ci.start_date + 978307200, 'unixepoch', 'localtime') = '{date_str}'
  AND c.flags NOT IN (2, 4, 5, 519)
ORDER BY ci.start_date;"""
        result = subprocess.run(
            ["sqlite3", db, query],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        output = result.stdout.strip()
        if not output:
            return f"No events on {date_str}."
        lines = []
        for row in output.split("\n"):
            parts = row.split("|")
            if len(parts) >= 3:
                summary, start, end = parts[0], parts[1], parts[2]
                lines.append(f"{start}-{end} {summary}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching calendar: {e}"


def create_calendar_event(title, date_str, time_str, duration_min, location="") -> str:
    """Create a calendar event via AppleScript (locale-independent date handling)."""
    try:
        parts = date_str.split("-")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        t_parts = time_str.split(":")
        hour, minute = int(t_parts[0]), int(t_parts[1])
        loc_prop = ""
        if location:
            loc_prop = f', location:"{location}"'
        script = f'''
tell application "Calendar"
    tell (first calendar whose name is not "")
        set evt_start to current date
        set year of evt_start to {year}
        set month of evt_start to {month}
        set day of evt_start to {day}
        set hours of evt_start to {hour}
        set minutes of evt_start to {minute}
        set seconds of evt_start to 0
        set evt_end to evt_start + ({duration_min} * minutes)
        make new event with properties {{summary:"{title}", start date:evt_start, end date:evt_end{loc_prop}}}
    end tell
end tell'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return f"Event created: {title} on {date_str} at {time_str} ({duration_min} min.)"
        return f"Error: {result.stderr.strip()}"
    except Exception as e:
        return f"Error creating event: {e}"


def delete_calendar_event(name, date_str=None) -> str:
    """Delete a calendar event by name (and optionally date)."""
    try:
        db = os.path.expanduser("~/Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb")
        if date_str:
            where = f"ci.summary LIKE '%{name}%' AND date(ci.start_date + 978307200, 'unixepoch', 'localtime') = '{date_str}'"
        else:
            where = f"ci.summary LIKE '%{name}%'"
        query = f"""
SELECT ci.summary, strftime('%Y-%m-%d %H:%M', ci.start_date + 978307200, 'unixepoch', 'localtime'), c.title
FROM CalendarItem ci
JOIN Calendar c ON ci.calendar_id = c.ROWID
WHERE {where} AND c.flags NOT IN (2, 4, 5, 519)
ORDER BY ci.start_date LIMIT 5;"""
        result = subprocess.run(["sqlite3", db, query], capture_output=True, text=True, timeout=10)
        if not result.stdout.strip():
            return f"No event matching '{name}' found."
        matches = result.stdout.strip().split("\n")
        first = matches[0].split("|")
        cal_name = first[2] if len(first) >= 3 else ""
        event_summary = first[0]
        event_date = first[1] if len(first) >= 2 else ""
        print(f"[CAL-DEL] Deleting '{event_summary}' from calendar '{cal_name}'")
        script = f'''
tell application "Calendar"
    tell calendar "{cal_name}"
        set evts to (every event whose summary contains "{event_summary}")
        set deleted to 0
        repeat with e in evts
            delete e
            set deleted to deleted + 1
        end repeat
        return deleted as string
    end tell
    reload calendars
end tell'''
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=45)
        count = result.stdout.strip()
        print(f"[CAL-DEL] AppleScript returned: code={result.returncode}, stdout='{count}', stderr='{result.stderr.strip()}'")
        if result.returncode == 0 and count and count != "0":
            import time
            time.sleep(1)
            verify = subprocess.run(["sqlite3", db, f"SELECT COUNT(*) FROM CalendarItem WHERE summary = '{event_summary}';"],
                                    capture_output=True, text=True, timeout=10)
            remaining = verify.stdout.strip()
            print(f"[CAL-DEL] Verify: {remaining} events remaining with that name")
            if remaining == "0":
                return f"Event '{event_summary}' ({event_date}) deleted."
            else:
                return f"Event '{event_summary}' deleted, but database still shows it. Possible iCloud sync delay — please wait a moment."
        return f"Event found but could not be deleted: {result.stderr.strip()}"
    except Exception as e:
        return f"Error deleting event: {e}"


def modify_calendar_event(name, orig_date, new_date=None, new_time=None, new_duration=None) -> str:
    """Modify a calendar event's date/time/duration."""
    try:
        db = os.path.expanduser("~/Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb")
        query = f"""
SELECT ci.summary, strftime('%Y-%m-%d', ci.start_date + 978307200, 'unixepoch', 'localtime'),
       strftime('%H:%M', ci.start_date + 978307200, 'unixepoch', 'localtime'),
       CAST(ROUND((ci.end_date - ci.start_date) / 60.0) AS INTEGER), c.title
FROM CalendarItem ci
JOIN Calendar c ON ci.calendar_id = c.ROWID
WHERE ci.summary LIKE '%{name}%'
  AND date(ci.start_date + 978307200, 'unixepoch', 'localtime') = '{orig_date}'
  AND c.flags NOT IN (2, 4, 5, 519)
LIMIT 1;"""
        result = subprocess.run(["sqlite3", db, query], capture_output=True, text=True, timeout=10)
        if not result.stdout.strip():
            return f"No event matching '{name}' on {orig_date} found."
        parts = result.stdout.strip().split("|")
        event_summary = parts[0]
        old_date = parts[1]
        old_time = parts[2]
        old_duration = int(parts[3])
        cal_name = parts[4]
        use_date = new_date or old_date
        use_time = new_time or old_time
        use_duration = int(new_duration) if new_duration else old_duration
        d = use_date.split("-")
        t = use_time.split(":")
        year, month, day = int(d[0]), int(d[1]), int(d[2])
        hour, minute = int(t[0]), int(t[1])
        script = f'''
tell application "Calendar"
    tell calendar "{cal_name}"
        set evts to (every event whose summary is "{event_summary}")
        repeat with e in evts
            set newStart to current date
            set year of newStart to {year}
            set month of newStart to {month}
            set day of newStart to {day}
            set hours of newStart to {hour}
            set minutes of newStart to {minute}
            set seconds of newStart to 0
            set start date of e to newStart
            set end date of e to newStart + ({use_duration} * minutes)
            return "OK"
        end repeat
    end tell
end tell'''
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and "OK" in result.stdout:
            changes = []
            if new_date and new_date != old_date:
                changes.append(f"date: {new_date}")
            if new_time and new_time != old_time:
                changes.append(f"time: {new_time}")
            if new_duration and int(new_duration) != old_duration:
                changes.append(f"duration: {new_duration} min.")
            change_str = ", ".join(changes) if changes else "updated"
            return f"Event '{event_summary}' modified: {change_str}"
        return f"Error: {result.stderr.strip()}"
    except Exception as e:
        return f"Error modifying event: {e}"


def get_reminders(list_name=None) -> str:
    """Get incomplete reminders via EventKit helper."""
    try:
        cmd = [REMINDERS_HELPER, "list"]
        if list_name:
            cmd.append(list_name)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() or "No open reminders."
    except Exception as e:
        return f"Error fetching reminders: {e}"


def create_reminder(title, due_date=None, list_name=None) -> str:
    """Create a reminder via EventKit helper."""
    try:
        cmd = [REMINDERS_HELPER, "create", title, due_date or "", list_name or ""]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()
        if result.returncode == 0 and output:
            return output
        return f"Error: {result.stderr.strip() or output}"
    except Exception as e:
        return f"Error creating reminder: {e}"


def complete_reminder(name) -> str:
    """Mark a reminder as complete via EventKit helper."""
    try:
        result = subprocess.run(
            [REMINDERS_HELPER, "complete", name],
            capture_output=True, text=True, timeout=15
        )
        output = result.stdout.strip()
        if result.returncode == 0 and output:
            return output
        return output or f"Error: {result.stderr.strip()}"
    except Exception as e:
        return f"Error: {e}"


def ask_claude(user_id: int, message: str) -> str:
    """Send message to Claude and return response."""
    if user_id not in conversations:
        conversations[user_id] = []

    conversations[user_id].append({"role": "user", "content": message})

    # Keep last 20 messages to save tokens
    if len(conversations[user_id]) > 20:
        conversations[user_id] = conversations[user_id][-20:]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=get_system_prompt(),
        messages=conversations[user_id]
    )

    reply = response.content[0].text
    conversations[user_id].append({"role": "assistant", "content": reply})

    # Check for commands in the response
    hue_matches = re.findall(r'\[HUE:([^\]]+)\]', reply)
    net_matches = re.findall(r'\[NET:([^\]]+)\]', reply)
    linkedin_matches = re.findall(r'\[LINKEDIN:(.*?)\]', reply, re.DOTALL)
    mail_matches = re.findall(r'\[MAIL:(\d+)\]', reply)
    cal_matches = re.findall(r'\[CAL:(\d+(?::-?\d+)?)\]', reply)
    cal_date_matches = re.findall(r'\[CAL-DATE:(\d{4}-\d{2}-\d{2})\]', reply)
    cal_new_matches = re.findall(r'\[CAL-NEW:([^\]]+)\]', reply)
    cal_del_matches = re.findall(r'\[CAL-DEL:([^\]]+)\]', reply)
    cal_mod_matches = re.findall(r'\[CAL-MOD:([^\]]+)\]', reply)
    rem_matches = re.findall(r'\[REM:([^\]]*)\]', reply)
    rem_new_matches = re.findall(r'\[REM-NEW:([^\]]+)\]', reply)
    rem_done_matches = re.findall(r'\[REM-DONE:([^\]]+)\]', reply)

    results = []
    for cmd in hue_matches:
        results.append(run_hue(cmd))
    for cmd in net_matches:
        cmd = cmd.strip().lower()
        if cmd in ("geräte", "devices"):
            results.append(get_network_devices())
        elif cmd == "scan":
            results.append(scan_network())
        elif cmd == "info":
            results.append(get_connection_info())
    for text in linkedin_matches:
        results.append(linkedin_post(text.strip()))
    for count in mail_matches:
        results.append(get_unread_emails(int(count)))
    for cal_param in cal_matches:
        cal_parts = cal_param.split(":")
        cal_days = int(cal_parts[0])
        cal_offset = int(cal_parts[1]) if len(cal_parts) > 1 else 0
        results.append(get_calendar_events(cal_days, cal_offset))
    for date_str in cal_date_matches:
        results.append(get_calendar_by_date(date_str))
    for params in cal_new_matches:
        parts = [p.strip() for p in params.split("|")]
        title = parts[0] if len(parts) > 0 else ""
        date = parts[1] if len(parts) > 1 else ""
        time = parts[2] if len(parts) > 2 else "12:00"
        duration = parts[3] if len(parts) > 3 else "60"
        location = parts[4] if len(parts) > 4 else ""
        results.append(create_calendar_event(title, date, time, int(duration), location))
    for params in cal_del_matches:
        parts = [p.strip() for p in params.split("|")]
        name = parts[0] if len(parts) > 0 else ""
        date_str = parts[1] if len(parts) > 1 and parts[1] else None
        results.append(delete_calendar_event(name, date_str))
    for params in cal_mod_matches:
        parts = [p.strip() for p in params.split("|")]
        name = parts[0] if len(parts) > 0 else ""
        orig_date = parts[1] if len(parts) > 1 else ""
        new_date = parts[2] if len(parts) > 2 and parts[2] else None
        new_time = parts[3] if len(parts) > 3 and parts[3] else None
        new_duration = parts[4] if len(parts) > 4 and parts[4] else None
        results.append(modify_calendar_event(name, orig_date, new_date, new_time, new_duration))
    for list_name in rem_matches:
        results.append(get_reminders(list_name.strip() or None))
    for params in rem_new_matches:
        parts = [p.strip() for p in params.split("|")]
        title = parts[0] if len(parts) > 0 else ""
        due = parts[1] if len(parts) > 1 and parts[1] else None
        lst = parts[2] if len(parts) > 2 and parts[2] else None
        results.append(create_reminder(title, due, lst))
    for name in rem_done_matches:
        results.append(complete_reminder(name.strip()))

    has_commands = (hue_matches or net_matches or linkedin_matches or mail_matches or
                    cal_matches or cal_date_matches or cal_new_matches or cal_del_matches or cal_mod_matches or
                    rem_matches or rem_new_matches or rem_done_matches)
    if has_commands:
        clean_reply = re.sub(r'\[(HUE|NET|LINKEDIN|MAIL|CAL|CAL-DATE|CAL-NEW|CAL-DEL|CAL-MOD|REM|REM-NEW|REM-DONE):.*?\]', '', reply, flags=re.DOTALL).strip()
        output = "\n".join(results)
        if clean_reply:
            return f"{clean_reply}\n\n{output}"
        return output

    return reply


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not ALLOWED_USERS:
        # First user to /start becomes admin
        ALLOWED_USERS.add(user_id)
        save_admins()
        await update.message.reply_text(
            f"Hello! You are now registered as admin (ID: {user_id}).\n"
            f"Just send me a message!"
        )
    elif user_id in ALLOWED_USERS:
        await update.message.reply_text("Hello! Just send me a message.")
    else:
        await update.message.reply_text("Access denied.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return

    msg = update.message.text
    await update.message.chat.send_action("typing")

    try:
        reply = ask_claude(user_id, msg)
        await update.message.reply_text(reply)
    except Exception as e:
        import traceback
        print(f"[ERROR] {traceback.format_exc()}")
        await update.message.reply_text(f"Error: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages: download OGG, convert to WAV, transcribe with Whisper, send to Claude."""
    import tempfile
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return

    await update.message.chat.send_action("typing")

    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
            ogg_path = ogg_file.name
            await file.download_to_drive(ogg_path)

        wav_path = ogg_path.replace(".ogg", ".wav")
        ffmpeg = os.path.expanduser("~/ffmpeg")
        subprocess.run([ffmpeg, "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path, "-y"],
                       capture_output=True, timeout=15)

        whisper = os.path.expanduser("~/whisper-cli")
        model = os.path.expanduser("~/ggml-base.bin")
        result = subprocess.run(
            [whisper, "-m", model, "-f", wav_path, "-l", "de", "--no-timestamps", "-np"],
            capture_output=True, text=True, timeout=30
        )
        transcript = result.stdout.strip()

        os.unlink(ogg_path)
        os.unlink(wav_path)

        if not transcript:
            await update.message.reply_text("Could not understand the voice message.")
            return

        print(f"[VOICE] Transcription: {transcript}")
        reply = ask_claude(user_id, transcript)
        await update.message.reply_text(reply)
    except Exception as e:
        import traceback
        print(f"[ERROR] Voice: {traceback.format_exc()}")
        await update.message.reply_text(f"Voice message error: {e}")


async def hue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct /hue command for quick light control."""
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return

    if not context.args:
        await update.message.reply_text("Usage: /hue [command]\ne.g. /hue status, /hue alles-aus")
        return

    cmd = " ".join(context.args)
    result = run_hue(cmd)
    await update.message.reply_text(result)


def morgen_briefing() -> str:
    """Build a morning briefing with calendar, reminders, and unread emails."""
    msg = "Good morning!\n\n"

    try:
        msg += "TODAY'S EVENTS:\n"
        msg += get_calendar_events(1)
        msg += "\n\n"
    except Exception:
        msg += "EVENTS: unavailable\n\n"

    try:
        msg += "REMINDERS:\n"
        msg += get_reminders()
        msg += "\n\n"
    except Exception:
        msg += "REMINDERS: unavailable\n\n"

    try:
        msg += "EMAILS:\n"
        msg += get_unread_emails(10)
    except Exception:
        msg += "EMAILS: unavailable"

    return msg


def abend_check() -> str:
    """Build the evening status message."""
    msg = "Evening check:\n\n"

    try:
        url = f"http://{HUE_IP}/api/{HUE_API_KEY}/groups"
        groups = json.loads(urllib.request.urlopen(url, timeout=5).read().decode())
        rooms_on = []
        for gid, g in groups.items():
            if g.get("type") == "Room" and g.get("state", {}).get("any_on"):
                rooms_on.append(g["name"])
        if rooms_on:
            msg += f"Lights on ({len(rooms_on)}):\n"
            for r in rooms_on:
                msg += f"  - {r}\n"
        else:
            msg += "All lights are off.\n"
    except Exception:
        msg += "Lights: unreachable\n"

    try:
        data = fritz_request("meshList")
        devices = data.get("data", {}).get("net", {}).get("devices", [])
        online = [d for d in devices if d.get("stateinfo", {}).get("online")]
        msg += f"\nDevices on network: {len(online)}"
    except Exception:
        msg += "\nNetwork: unreachable"

    return msg


async def scheduled_abend_check(context: ContextTypes.DEFAULT_TYPE):
    """Send evening check to all admins at 23:00."""
    msg = abend_check()
    for user_id in ALLOWED_USERS:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg)
        except Exception:
            pass


async def scheduled_morgen_briefing(context: ContextTypes.DEFAULT_TYPE):
    """Send morning briefing to all admins at 7:00."""
    msg = morgen_briefing()
    for user_id in ALLOWED_USERS:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg)
        except Exception:
            pass


def main():
    load_admins()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hue", hue_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Schedule daily jobs
    job_queue = app.job_queue
    cet = datetime.timezone(datetime.timedelta(hours=1))
    job_queue.run_daily(scheduled_morgen_briefing, time=datetime.time(hour=7, minute=0, tzinfo=cet))
    job_queue.run_daily(scheduled_abend_check, time=datetime.time(hour=23, minute=0, tzinfo=cet))

    print("Bot running... (Morning briefing 7:00, Evening check 23:00)")
    app.run_polling()


if __name__ == "__main__":
    main()
