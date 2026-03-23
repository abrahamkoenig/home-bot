#!/usr/bin/env python3
"""Personal AI home assistant on Telegram — controls Philips Hue lights,
monitors network, posts to LinkedIn, checks emails, and more.
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

# FRITZ!Box config
FRITZ_IP = os.environ.get("FRITZ_IP", "192.168.178.1")
FRITZ_USER = os.environ.get("FRITZ_USER", "your-fritz-user")
FRITZ_PASS = os.environ.get("FRITZ_PASS", "your-fritz-password")

# Only allow your own Telegram user ID (set after first /start)
ALLOWED_USERS = set()
ADMIN_FILE = os.path.expanduser("~/.telegram_bot_admins.json")

# Conversation history per user
conversations = {}

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

SYSTEM_PROMPT = """You are a personal home assistant on Telegram. You respond concisely and helpfully.

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

Respond with [HUE:command] for light commands, e.g. [HUE:alles-aus] or [HUE:wohnzimmer an].
Respond with [NET:command] for network commands:
- [NET:geräte] for connected devices
- [NET:scan] for a network scan
- [NET:info] for connection info
Respond with [LINKEDIN:text] to post to LinkedIn.
Respond with [MAIL:count] to fetch emails, e.g. [MAIL:5]."""


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
    """Get unread emails from macOS Mail app via AppleScript."""
    try:
        script = f'''
tell application "Mail"
    set unreadMessages to (messages of inbox whose read status is false)
    set output to ""
    set msgCount to 0
    repeat with msg in unreadMessages
        if msgCount >= {limit} then exit repeat
        set output to output & "FROM: " & (sender of msg) & linefeed
        set output to output & "SUBJECT: " & (subject of msg) & linefeed
        set output to output & "DATE: " & (date received of msg as string) & linefeed
        set output to output & "---" & linefeed
        set msgCount to msgCount + 1
    end repeat
    if msgCount = 0 then
        return "No unread emails."
    end if
    set totalUnread to count of unreadMessages
    set output to output & "TOTAL: " & totalUnread & " unread emails"
    return output
end tell'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip() or "No unread emails."
    except Exception as e:
        return f"Error fetching emails: {e}"


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
        system=SYSTEM_PROMPT,
        messages=conversations[user_id]
    )

    reply = response.content[0].text
    conversations[user_id].append({"role": "assistant", "content": reply})

    # Check for commands in the response
    hue_matches = re.findall(r'\[HUE:([^\]]+)\]', reply)
    net_matches = re.findall(r'\[NET:([^\]]+)\]', reply)
    linkedin_matches = re.findall(r'\[LINKEDIN:(.*?)\]', reply, re.DOTALL)
    mail_matches = re.findall(r'\[MAIL:(\d+)\]', reply)

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

    if hue_matches or net_matches or linkedin_matches or mail_matches:
        clean_reply = re.sub(r'\[(HUE|NET|LINKEDIN|MAIL):.*?\]', '', reply, flags=re.DOTALL).strip()
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
        await update.message.reply_text(f"Error: {e}")


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
    """Build a morning briefing with unread emails."""
    msg = "Good morning!\n\n"
    msg += get_unread_emails(10)
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

    # Schedule daily jobs
    job_queue = app.job_queue
    cet = datetime.timezone(datetime.timedelta(hours=1))
    job_queue.run_daily(scheduled_morgen_briefing, time=datetime.time(hour=7, minute=0, tzinfo=cet))
    job_queue.run_daily(scheduled_abend_check, time=datetime.time(hour=23, minute=0, tzinfo=cet))

    print("Bot running... (Morning briefing 7:00, Evening check 23:00)")
    app.run_polling()


if __name__ == "__main__":
    main()
