# 🎵 Telegram Music Bot

> Enterprise-grade Telegram voice chat music streaming bot — Heroku-ready, async, production-grade.

---

## ✨ Features

| Category | Details |
|---|---|
| **Sources** | YouTube, Spotify (tracks/playlists/albums), SoundCloud, Direct URLs, Telegram audio files |
| **Queue** | Persistent per-group queue, priority play, shuffle, loop, history, pagination |
| **Controls** | Pause, Resume, Skip, Stop, Seek, Volume, Mute, Speed |
| **Inline UI** | Now-playing cards, volume controls, lyrics, download buttons, queue pager |
| **Admin** | Global ban, sudo users, maintenance mode, broadcast, logs channel |
| **Playlists** | Save/load/delete named playlists from any group queue |
| **Analytics** | Daily stats, leaderboard, playback history |
| **Security** | Anti-flood, rate limiting, anti-spam, env validation |
| **Auto-recovery** | Stream watchdog, idle auto-leave, crash handling |
| **Deployment** | Heroku (worker dyno), Docker, local venv |

---

## 📋 Commands

### 🎵 Music
| Command | Description |
|---|---|
| `/play [song/URL]` | Play audio from YouTube, Spotify, or direct link |
| `/vplay [song/URL]` | Play video in voice chat |
| `/song [title]` | Search YouTube and pick from results |
| `/radio [URL]` | Start a live radio/stream URL |
| `/replay` | Replay the current track |
| `/lyrics` | Get lyrics for the current track |

### 🎛 Playback Controls
| Command | Description |
|---|---|
| `/pause` | Pause playback |
| `/resume` | Resume playback |
| `/skip` | Skip to next track |
| `/stop` | Stop and leave voice chat |
| `/seek [seconds]` | Seek to position |
| `/loop` | Toggle loop mode |
| `/shuffle` | Shuffle the queue |
| `/volume [0-200]` | Set volume |
| `/mute` / `/unmute` | Mute/unmute |

### 📋 Queue
| Command | Description |
|---|---|
| `/queue` | View current queue with pagination |
| `/remove [pos]` | Remove track at position |
| `/clearqueue` | Clear all queued tracks |
| `/history` | View recent playback history |

### 📂 Playlists
| Command | Description |
|---|---|
| `/saveplaylist [name]` | Save current queue as playlist |
| `/loadplaylist [name]` | Load a saved playlist |
| `/myplaylists` | List your saved playlists |
| `/deleteplaylist [name]` | Delete a playlist |

### ⚙️ Admin (Group Admins)
| Command | Description |
|---|---|
| `/settings` | View/toggle chat settings |
| `/clean` | Clean bot messages |

### 🛡 Sudo (Sudo Users)
| Command | Description |
|---|---|
| `/gban [id]` | Globally ban a user |
| `/ungban [id]` | Remove global ban |
| `/broadcast` | Broadcast to all users |
| `/stats` | Bot statistics |
| `/leaderboard` | Top listeners today |
| `/maintenance` | Toggle maintenance mode |
| `/restart` | Restart the bot |
| `/update` | Pull latest changes from GitHub |

### 👑 Owner Only
| Command | Description |
|---|---|
| `/addadmin [id]` | Add a sudo user |
| `/removeadmin [id]` | Remove a sudo user |
| `/eval [code]` | Execute Python code |
| `/shell [cmd]` | Execute shell command |

---

## 🚀 Deployment

### Prerequisites
- Telegram API credentials from [my.telegram.org](https://my.telegram.org/apps)
- Bot token from [@BotFather](https://t.me/BotFather)
- [MongoDB Atlas](https://cloud.mongodb.com) free cluster
- Heroku account (free/eco/basic dyno)

---

### Step 1 — Get Credentials

1. Go to [my.telegram.org](https://my.telegram.org/apps) → create app → copy **API_ID** and **API_HASH**
2. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy **BOT_TOKEN**
3. Generate a string session for the assistant userbot:
   ```bash
   pip install pyrogram TgCrypto
   python generate_session.py
   ```
   Copy the output as **STRING_SESSION**

4. Create a MongoDB Atlas cluster → Database → Connect → copy the **connection URI**

---

### Step 2 — Heroku Deployment

#### Option A: One-Click (app.json)
Click the Deploy button if hosted on GitHub, or follow Option B.

#### Option B: Manual

```bash
# 1. Install Heroku CLI
# https://devcenter.heroku.com/articles/heroku-cli

# 2. Login
heroku login

# 3. Create app
heroku create your-music-bot-name

# 4. Add buildpacks (ORDER MATTERS)
heroku buildpacks:add heroku/python
heroku buildpacks:add https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git
heroku buildpacks:add heroku-community/apt

# 5. Attach Redis add-on
heroku addons:create heroku-redis:mini

# 6. Set all environment variables
heroku config:set API_ID=12345678
heroku config:set API_HASH=abcdef...
heroku config:set BOT_TOKEN=123456:ABC...
heroku config:set STRING_SESSION=BQAFAQABz...
heroku config:set MONGO_DB_URI="mongodb+srv://..."
heroku config:set REDIS_URI=$(heroku config:get REDIS_URL)
heroku config:set LOG_GROUP_ID=-1001234567890
heroku config:set OWNER_ID=987654321
heroku config:set DURATION_LIMIT=180
heroku config:set STREAM_QUALITY=128
heroku config:set AUTO_LEAVING_ASSISTANT=True

# 7. Deploy
git init
git add .
git commit -m "Initial deploy"
heroku git:remote -a your-music-bot-name
git push heroku main

# 8. Scale worker dyno (no web dyno needed)
heroku ps:scale web=0 worker=1

# 9. Check logs
heroku logs --tail
```

---

### Step 3 — Local Development

```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/YOUR_REPO
cd musicbot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate    # Linux/Mac
# venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg
# Ubuntu/Debian: sudo apt install ffmpeg
# macOS:         brew install ffmpeg
# Windows:       https://ffmpeg.org/download.html

# Copy and fill env file
cp .env.example .env
nano .env

# Run
python main.py
```

---

### Step 4 — Docker

```bash
# Build
docker build -t musicbot .

# Run
docker run -d --name musicbot \
  --env-file .env \
  musicbot

# Logs
docker logs -f musicbot
```

---

## ⚙️ Configuration Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `API_ID` | ✅ | — | Telegram API ID |
| `API_HASH` | ✅ | — | Telegram API Hash |
| `BOT_TOKEN` | ✅ | — | Bot token from BotFather |
| `STRING_SESSION` | ✅ | — | Pyrogram assistant session |
| `MONGO_DB_URI` | ✅ | — | MongoDB Atlas URI |
| `REDIS_URI` | ✅ | — | Redis connection URI |
| `LOG_GROUP_ID` | ✅ | — | Telegram log group ID |
| `OWNER_ID` | ✅ | — | Your Telegram user ID |
| `SPOTIFY_CLIENT_ID` | ❌ | — | Spotify API client ID |
| `SPOTIFY_CLIENT_SECRET` | ❌ | — | Spotify API client secret |
| `DURATION_LIMIT` | ❌ | `180` | Max track duration (minutes) |
| `STREAM_QUALITY` | ❌ | `128` | Audio bitrate (kbps) |
| `AUTO_LEAVING_ASSISTANT` | ❌ | `True` | Leave VC when queue empties |
| `QUEUE_LIMIT` | ❌ | `100` | Max tracks per group queue |
| `SUDO_USERS` | ❌ | — | Space-separated sudo user IDs |

---

## 🔧 Troubleshooting

**Bot doesn't respond**
- Check `heroku logs --tail` for errors
- Confirm worker dyno is running: `heroku ps`
- Verify `BOT_TOKEN` is correct

**"FloodWait" errors**
- Normal on startup; bot will auto-retry
- Avoid spamming commands during initial setup

**Music doesn't play / stream fails**
- Confirm assistant userbot is in the voice chat
- Check `STRING_SESSION` is valid (re-generate if needed)
- Verify FFmpeg is installed: `heroku run ffmpeg -version`

**MongoDB connection errors**
- Whitelist `0.0.0.0/0` in MongoDB Atlas Network Access
- Confirm URI includes database name: `.../musicbot?...`

**Redis errors on Heroku**
- Heroku sets `REDIS_URL`, but the app reads `REDIS_URI`
- Fix: `heroku config:set REDIS_URI=$(heroku config:get REDIS_URL)`

**Spotify links not working**
- Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`
- Get credentials at [developer.spotify.com](https://developer.spotify.com/dashboard)

---

## 🏗 Project Structure

```
musicbot/
├── bot/
│   ├── config/         # Configuration & env validation
│   ├── core/           # Bot lifecycle, client setup
│   ├── database/       # MongoDB & Redis layers
│   ├── handlers/       # Command handlers
│   ├── helpers/        # Keyboards, formatters, decorators
│   ├── plugins/        # Optional feature plugins (playlists)
│   ├── security/       # Anti-flood, middleware
│   ├── streaming/      # Queue engine & PyTgCalls engine
│   └── utils/          # Scheduler, background jobs
├── cache/              # Temporary audio files
├── logs/               # Rotating log files
├── main.py             # Entry point
├── generate_session.py # String session generator
├── requirements.txt
├── Procfile            # Heroku process definition
├── runtime.txt         # Python version for Heroku
├── Aptfile             # System packages (FFmpeg)
├── Dockerfile
├── app.json            # Heroku app manifest
└── .env.example
```

---

## 📜 License

MIT License — free to use, modify, and distribute.

---

## 🙏 Credits

- [Pyrogram](https://github.com/pyrogram/pyrogram) — Telegram MTProto client
- [PyTgCalls](https://github.com/pytgcalls/pytgcalls) — Voice chat streaming
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — Media extraction
- [Motor](https://github.com/mongodb/motor) — Async MongoDB driver
- [aioredis](https://github.com/aio-libs/aioredis-py) — Async Redis client
