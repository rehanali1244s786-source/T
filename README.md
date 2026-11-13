# Telegram Music + Video Bot (v3 — aiogram 3 Edition)

Complete Telegram Music & 480p Video Downloader Bot migrated to **aiogram 3.x**, featuring coloured Telegram buttons (`success` / `danger` / `primary`), animated status frames and live `yt-dlp` progress bars, bordered info tables, AudD song recognition, lrclib lyrics, MusicBrainz artist pages & release alerts, JazzCash/Easypaisa Premium management, and full group administration.

---

## Project Structure

```text
music-bot-railway/
├── main.py                  # Entry point (Bot, Dispatcher, middlewares, startup/shutdown)
├── config.py                # Environment variables, defaults, and constants
├── db.py                    # JSON storage, atomic save, debounced saver, and state helpers
├── i18n.py                  # English, Urdu, and Hindi translations + tr() / L()
├── animations.py            # Animation frames, delays, progress bar, and bordered tables
├── keyboards.py             # InlineKeyboardBuilder keyboards, CallbackData factories, Btn()
├── middlewares.py           # GateMiddleware (bans/force-join) & CreditRequestMiddleware
├── services/
│   ├── __init__.py
│   ├── youtube.py           # yt-dlp search, metadata, download + progress hooks & priority queue
│   ├── musicbrainz.py       # MusicBrainz artist, release-group & recording lookups
│   ├── bpm.py               # Deezer BPM, GetSongBPM, and optional librosa audio analysis
│   ├── lyrics.py            # lrclib.net lyrics lookup and title cleaning
│   └── audd.py              # AudD voice/audio/video song recognition
├── handlers/
│   ├── __init__.py
│   ├── user.py              # /start, /menu, /help, /id, /lang, /stats + interactive menu
│   ├── song.py              # /song, /lyrics, song cards, downloads, info, BPM, share
│   ├── search.py            # /search, animated query search, result picker
│   ├── admin.py             # /admin panel, force-join & premium/sponsor config flows
│   ├── groups.py            # /groups manager, broadcast, /ban, /unban, /warn, /approve, /brand
│   ├── premium.py           # /premium, JazzCash/Easypaisa proof flows, /givepremium, /removepremium
│   ├── artist.py            # /artist page, latest releases, top songs
│   ├── follow.py            # /follow, /following, /invite, release_watcher loop
│   ├── inline.py            # Inline mode (@bot song name)
│   └── recognize.py         # /find, voice/audio recognition, unknown command suggestions, message router
├── vps/
│   ├── run.sh               # Self-hosted Linux setup & launcher script
│   └── musicbot.service     # systemd unit file for VPS deployments
├── Dockerfile               # Python 3.12-slim + ffmpeg + nodejs worker container
├── railway.json             # Railway Dockerfile builder & restart policy
├── requirements.txt         # Python dependencies (aiogram>=3.13,<4, yt-dlp, httpx, python-dotenv)
├── .env.example             # Complete environment variable template
├── .gitignore
├── .dockerignore
└── musicbot_data.example.json
```

---

## Deploying on Railway (Recommended)

This bot runs as a background **polling worker** (no HTTP port is needed).

1. **Push to GitHub**
   Create a new private GitHub repository and push the contents of `music-bot-railway/` to it:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: aiogram 3 music bot"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```
2. **Create a Railway Project**
   Open [Railway](https://railway.app/) → **New Project** → **Deploy from GitHub repo** → select your repository.
3. **Add Environment Variables**
   Open your service in Railway → **Variables** tab → add at least:
   - `BOT_TOKEN` = your token from `@BotFather`
   - `ADMIN_IDS` = your Telegram numeric user ID (send `/id` to the bot to check)
   - `DATA_FILE` = `/data/musicbot_data.json`
   - Any optional variables from `.env.example` (`AUDD_TOKEN`, `MENU_BANNER_URL`, `BOT_VERSION`, `GETSONGBPM_KEY`, etc.).
4. **Mount a Persistent Volume at `/data`**
   Right-click the service card on the Railway canvas (or open **Settings → Volumes**) → **Add Volume** → set the **Mount Path** to:
   ```text
   /data
   ```
   This guarantees `musicbot_data.json` (users, premium subscriptions, groups, referrals, and file ID caches) survives every redeploy and restart.
5. **Verify Deployment Logs**
   Open the **Deployments → View Logs** tab and verify that you see:
   ```text
   INFO | MusicBot | Bot started...
   ```

---

## Self-Hosting on a Linux VPS (Optional)

If you prefer hosting on Ubuntu/Debian instead of Railway:
```bash
sudo apt update && sudo apt install -y python3 python3-venv ffmpeg nodejs
cp .env.example .env && nano .env
bash vps/run.sh
```
To run 24/7 with `systemd`, edit paths in `vps/musicbot.service`, copy it to `/etc/systemd/system/musicbot.service`, and run `sudo systemctl daemon-reload && sudo systemctl enable --now musicbot`.
