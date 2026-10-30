# f1paper

Automated, configurable Formula 1 wallpaper acquisition tool.

`f1paper` detects the currently active F1 race weekend, gathers candidate
photos from Formula1.com galleries, Reddit (`r/formula1`), and official team
accounts on X/Twitter and Instagram, picks the one that best matches your
chosen screen resolution while respecting your per-team and per-driver
on/off/weight preferences, and sets it as your desktop wallpaper. Works on
Windows and Linux.

## How it works

1. `schedule.py` asks the free [jolpica-f1 API](https://api.jolpi.ca/) (an
   Ergast-compatible, keyless successor) for the current season's calendar
   and determines whether a race weekend is currently active.
2. If no weekend is active, the current wallpaper is left unchanged.
3. Each enabled source in `f1paper/sources/` returns candidate photos tagged
   with the team(s)/driver(s) pictured (via caption/alt-text/post-title
   matching against the current roster).
4. Candidates are downloaded, their real pixel dimensions and a perceptual
   hash are computed, then `selection.py` filters out disabled teams/drivers,
   scores the rest by resolution/aspect fit, and makes a weighted-random pick.
5. The chosen image is cropped/resized to exactly fill your target
   resolution and set as the wallpaper.

## Installation

```bash
python -m venv .venv
. .venv/Scripts/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Copy the example config and environment files and fill in credentials:

```bash
cp .env.example .env
```

### Credentials you'll need

- **Reddit** (required for the reddit source): create a free "script" app at
  <https://www.reddit.com/prefs/apps> and set `REDDIT_CLIENT_ID` /
  `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` in `.env`.
- **X/Twitter** (required for the twitter source): this uses
  [twscrape](https://github.com/vladkens/twscrape), which authenticates as a
  real logged-in X account rather than the official (paid) API. Add at least
  one account to its pool before running:

  ```bash
  twscrape add_accounts accounts.txt username:password:email:email_password
  twscrape login_accounts
  ```

  Then point `TWSCRAPE_DB_PATH` at the resulting sqlite file in `.env`.
- **Instagram** (optional, reduces rate-limiting): set `INSTAGRAM_USERNAME` /
  `INSTAGRAM_PASSWORD` in `.env`. Public profiles also work anonymously but
  are heavily throttled by Instagram.

> **Note:** the X/Twitter and Instagram sources rely on unofficial,
> community-maintained libraries that call undocumented endpoints. They can
> break when those platforms change their internal APIs and may need
> occasional maintenance (handle lists in `twitter_source.py` /
> `instagram_source.py` may also need updating each season).

## Usage

```bash
# One-off run for the current race weekend, auto-detecting your resolution
f1paper run

# Force a run even outside an active race weekend (uses the most recent one)
f1paper run --force

# Override the target resolution and just preview without setting it
f1paper run --resolution 3440x1440 --dry-run

# See current configuration
f1paper config show

# Turn a team off entirely
f1paper config team mercedes --disable

# Make Ferrari twice as likely to be picked
f1paper config team ferrari --weight 200

# Toggle an individual driver
f1paper config driver norris --disable

# Refresh the team/driver roster from the current season
f1paper config sync-roster

# Disable a source temporarily (e.g. if Instagram scraping breaks)
f1paper config source instagram --disable

# Set a fixed target resolution instead of auto-detecting
f1paper config resolution 2560x1440

# Install an automatic daily refresh (Task Scheduler on Windows, systemd timer on Linux)
f1paper install-schedule --time 09:00

# Clear the "recently used" history so repeats are allowed again
f1paper history clear
```

Configuration lives in `%APPDATA%\f1paper\config.yaml` on Windows or
`~/.config/f1paper/config.yaml` on Linux (override with `F1PAPER_CONFIG_DIR`).
See `config.example.yaml` for the full schema.

## Development

```bash
pytest
```

## Caveats

- Formula1.com photos and official team social media content are copyrighted
  editorial/marketing material; this tool is intended for personal wallpaper
  use only, not redistribution.
- The Formula1.com gallery scraper (`f1_official.py`) depends on the site's
  current HTML structure and may need selector updates if the site changes.
