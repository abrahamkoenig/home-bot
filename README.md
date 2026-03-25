# Home Bot

A personal AI home assistant running on Telegram. Chat naturally to control your smart home, monitor your network, post to LinkedIn, check your emails, manage your calendar and reminders — all from one bot, powered by Claude.

## Features

- **Smart Lights** — Control Philips Hue lights via natural language ("Turn off the kitchen") or scenes ("Movie mode", "Good night")
- **Network Monitoring** — Check connected devices and connection status via FRITZ!Box
- **LinkedIn Integration** — Post to LinkedIn and get AI-drafted comments for engagement
- **Email Briefing** — Check unread emails via IMAP on demand or in the daily morning summary
- **Calendar** — View, create, modify, and delete calendar events via Apple Calendar (sqlite3 + AppleScript)
- **Reminders** — View, create, and complete reminders via Apple Reminders (EventKit)
- **Scheduled Automations** — Morning briefing at 7:00 (calendar + reminders + emails), evening light check at 23:00
- **Access Control** — First user to `/start` becomes admin; no one else can use the bot

## Architecture

```
Telegram → telegram_bot.py → Claude API (brain)
                            → hue.py (lights)
                            → FRITZ!Box API (network)
                            → LinkedIn API (posts)
                            → IMAP (emails)
                            → sqlite3 + AppleScript (calendar)
                            → reminders_helper (EventKit binary)
```

## Setup

### Prerequisites

- Python 3.9+
- macOS (for calendar and reminders integration)
- Philips Hue Bridge
- FRITZ!Box router (for network monitoring)
- Swift compiler (for building reminders helper)

### Installation

```bash
pip install -r requirements.txt
```

> **Note:** python-telegram-bot v22+ has compatibility issues with Python 3.9 when using the job queue. The requirements.txt pins v21.x which works reliably.

Build the reminders helper (uses EventKit instead of AppleScript to avoid iCloud sync freezes):

```bash
swiftc reminders_helper.swift -o ~/reminders_helper -framework EventKit
```

> On first run, macOS will prompt for Reminders access — grant it.

### Configuration

Set environment variables or edit the config section in `telegram_bot.py`:

```bash
export TELEGRAM_TOKEN="your-telegram-bot-token"
export CLAUDE_API_KEY="your-claude-api-key"
export HUE_IP="192.168.x.x"
export HUE_API_KEY="your-hue-api-key"
export FRITZ_IP="192.168.178.1"
export FRITZ_USER="your-fritz-user"
export FRITZ_PASS="your-fritz-password"
export IMAP_SERVER="imap.mail.me.com"
export IMAP_USER="your-email@icloud.com"
export IMAP_PASS="your-app-specific-password"
```

**Telegram Bot Token:** Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, and follow the steps.

**Claude API Key:** Get one at [console.anthropic.com](https://console.anthropic.com).

**Hue API Key:** Press the link button on your Hue Bridge, then:
```bash
curl -X POST http://YOUR_HUE_IP/api -d '{"devicetype":"home-bot"}'
```

**LinkedIn:** Run `linkedin_auth.py` to complete the OAuth2 flow.

**Email (iCloud):** Generate an app-specific password at [appleid.apple.com](https://appleid.apple.com) → Sign-In & Security → App-Specific Passwords.

**Calendar:** Requires Full Disk Access for `/bin/bash` (System Settings → Privacy & Security → Full Disk Access) to read the Calendar sqlite database.

### Run

```bash
python3 telegram_bot.py
```

### Run as a macOS service (auto-start on boot)

1. Edit `run_telegram_bot.sh` and `com.koenigreich.telegrambot.plist` to match your paths
2. Copy the files into place:

```bash
cp run_telegram_bot.sh ~/run_telegram_bot.sh
chmod +x ~/run_telegram_bot.sh
cp com.koenigreich.telegrambot.plist ~/Library/LaunchAgents/
```

3. Load the service:

```bash
launchctl load ~/Library/LaunchAgents/com.koenigreich.telegrambot.plist
```

> **Important:** The LaunchAgent uses a wrapper script instead of calling the venv python directly. This is necessary because macOS resolves venv symlinks to the system Python, which breaks package imports. The wrapper script activates the venv properly before starting the bot.

## Usage

Just chat with the bot in Telegram:

- "Turn off all lights"
- "Who's on the WiFi?"
- "Post to LinkedIn: Excited about AI home automation!"
- "Do I have new emails?"
- "What's on my calendar today?"
- "Create a meeting tomorrow at 2pm"
- "Move the meeting to Thursday"
- "Delete the coffee appointment"
- "What reminders do I have?"
- "Remind me to call the dentist on Friday"
- "Dentist done"

## License

MIT
