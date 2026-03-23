# Home Bot

A personal AI home assistant running on Telegram. Chat naturally to control your smart home, monitor your network, post to LinkedIn, and check your emails — all from one bot, powered by Claude.

## Features

- **Smart Lights** — Control Philips Hue lights via natural language ("Turn off the kitchen") or scenes ("Movie mode", "Good night")
- **Network Monitoring** — Check connected devices and connection status via FRITZ!Box
- **LinkedIn Integration** — Post to LinkedIn and get AI-drafted comments for engagement
- **Email Briefing** — Check unread emails on demand or get a daily morning summary
- **Scheduled Automations** — Morning briefing at 7:00, evening light check at 23:00
- **Access Control** — First user to `/start` becomes admin; no one else can use the bot

## Architecture

```
Telegram → telegram_bot.py → Claude API (brain)
                            → hue.py (lights)
                            → FRITZ!Box API (network)
                            → LinkedIn API (posts)
                            → macOS Mail (emails via AppleScript)
```

## Setup

### Prerequisites

- Python 3.9+
- macOS (for email integration via AppleScript)
- Philips Hue Bridge
- FRITZ!Box router (for network monitoring)

### Installation

```bash
pip install python-telegram-bot[job-queue] anthropic
```

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
```

**Telegram Bot Token:** Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, and follow the steps.

**Claude API Key:** Get one at [console.anthropic.com](https://console.anthropic.com).

**Hue API Key:** Press the link button on your Hue Bridge, then:
```bash
curl -X POST http://YOUR_HUE_IP/api -d '{"devicetype":"home-bot"}'
```

**LinkedIn:** Run `linkedin_auth.py` to complete the OAuth2 flow.

### Run

```bash
python3 telegram_bot.py
```

## Usage

Just chat with the bot in Telegram:

- "Turn off all lights"
- "Who's on the WiFi?"
- "Post to LinkedIn: Excited about AI home automation!"
- "Do I have new emails?"
- "Write me a comment for this LinkedIn post: [paste]"

## License

MIT
