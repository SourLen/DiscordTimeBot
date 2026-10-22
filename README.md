# DiscordTimeBot

Tracks how long members spend in your server's voice channels, and turns that
into leaderboards, personal stats, milestone roles and a weekly recap.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.4%2B-5865F2)](https://github.com/Rapptz/discord.py)
[![Tests](https://img.shields.io/badge/tests-83%20passing-brightgreen)](tests/)
[![Code style](https://img.shields.io/badge/lint-ruff-261230)](https://docs.astral.sh/ruff/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## What it looks like

```
┌──────────────────────────────────────────────┐
│  Voice time — this week            [embed]   │
├──────────────────────────────────────────────┤
│  🥇 Luther        — 19h 42m                  │
│  🥈 kadeeq        — 14h 08m                  │
│  🥉 XanaX         — 11h 55m                  │
│  ` 4.` someoneelse — 6h 31m                  │
│  ` 5.` **you**     — 4h 02m                  │
│                                              │
│  5 members shown                             │
└──────────────────────────────────────────────┘
```

One embed per leaderboard, not one message per member.

## Features

- **Voice time tracking** that survives restarts, crashes, channel switches and
  missed gateway events.
- **Time windows** — every leaderboard and stat works for today, this week,
  this month, this year or all time, resolved in *your* timezone.
- **Per-channel breakdown** — see where a member actually spends their time.
- **Milestone roles** — automatically grant a role when someone crosses a
  threshold (`10h=Regular,100h=Veteran`).
- **Weekly digest** — a scheduled recap of last week's top 10, posted to a
  channel you choose.
- **Data you control** — `/export` your own sessions as CSV, `/forget` to
  delete everything and stop being tracked.
- **Slash commands only**, so the bot never needs the Message Content intent.
- **One runtime dependency** (`discord.py`) and a plain SQLite file for storage.

## Commands

| Command | Who can use it | What it does |
| --- | --- | --- |
| `/time [member] [period]` | everyone | Total voice time, plus the live session if they're in a channel right now |
| `/top [limit] [period]` | everyone | Leaderboard, up to 25 members, in a single embed |
| `/rank [member] [period]` | everyone | Where someone places |
| `/stats [member]` | everyone | Today / week / month / all-time side by side, plus favourite channels |
| `/serverstats [period]` | everyone | Total hours, active members, average per member |
| `/milestones [member]` | everyone | Milestone ladder and progress to the next role |
| `/export` | everyone | Your own sessions as a CSV, sent privately |
| `/forget` | everyone | Delete your data and stop tracking (with a confirmation step) |
| `/trackme` | everyone | Resume tracking after `/forget` |
| `/botinfo` | everyone | How this instance is configured and how many people are being tracked |
| `/digest` | Manage Server | Post last week's recap immediately |
| `/syncroles` | Manage Server | Re-check milestone roles for every tracked member |
| `/resetmember <member>` | Manage Server | Delete one member's tracked time |

`period` is one of `all time`, `today`, `this week`, `this month`, `this year`.

## Quick start

**1. Create the application**

Go to the [Discord Developer Portal](https://discord.com/developers/applications)
→ **New Application** → **Bot** → **Reset Token**, and copy the token.

On the same **Bot** page, under *Privileged Gateway Intents*, enable
**Server Members Intent**. That is the only privileged intent this bot needs —
Message Content stays off.

**2. Invite the bot**

Under **OAuth2 → URL Generator**, tick `bot` and `applications.commands`. For
permissions, `View Channels` and `Send Messages` are enough; add
`Manage Roles` only if you want milestone roles.

**3. Install**

```bash
git clone https://github.com/SourLen/DiscordTimeBot.git
cd DiscordTimeBot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**4. Configure**

```bash
cp .env.example .env
```

Put your token in `DISCORD_TOKEN`. While setting things up, also set
`GUILD_IDS` to your server's ID so slash commands appear immediately instead of
waiting for Discord's global command propagation.

**5. Run**

```bash
python main.py
```

You should see `Logged in as ...` and `Synced 13 command(s)`.

## Configuration

Everything is read from the environment, so a `.env` file, a systemd unit and a
container all work the same way. Existing environment variables always win over
`.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DISCORD_TOKEN` | *(required)* | Bot token |
| `GUILD_IDS` | *(empty)* | Comma-separated server IDs for instant command sync |
| `DATABASE_PATH` | `data/timebot.db` | Where the SQLite file lives |
| `EXCLUDED_CHANNEL_IDS` | *(empty)* | Voice channels that never count |
| `TRACK_AFK_CHANNEL` | `false` | Count time in the server's AFK channel |
| `IGNORE_DEAFENED` | `true` | Pause the clock while a member is deafened |
| `IGNORE_BOTS` | `true` | Never record bot accounts |
| `MIN_SESSION_SECONDS` | `10` | Discard sessions shorter than this |
| `TIMEZONE` | `UTC` | IANA zone defining "today"/"this week" and when the digest posts |
| `RECONCILE_INTERVAL_SECONDS` | `300` | Self-heal sweep and heartbeat interval |
| `MILESTONES` | *(empty)* | `10h=Regular,100h=Veteran,500h=Voice Gremlin` |
| `DIGEST_CHANNEL_ID` | *(empty)* | Channel for the weekly recap; empty disables it |
| `DIGEST_WEEKDAY` / `DIGEST_HOUR` | `0` / `18` | When to post (0 = Monday, hour in `TIMEZONE`) |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Milestone roles

```env
MILESTONES=10h=Regular,100h=Veteran,500h=Voice Gremlin
```

The roles must already exist, and the bot's own top role must sit **above**
them in the role list — Discord will not let a bot assign a role at or above
its own. Durations accept `w`, `d`, `h`, `m`, `s` and combinations like
`1d12h`. If a role is missing or unreachable the bot logs a warning and keeps
tracking; nothing breaks.

## How tracking works

A member's clock runs when **all** of these hold:

- they are connected to a voice or stage channel in the server,
- that channel is not in `EXCLUDED_CHANNEL_IDS`,
- that channel is not the server's AFK channel (unless `TRACK_AFK_CHANNEL`),
- they are not deafened (unless `IGNORE_DEAFENED=false`),
- they are not a bot (unless `IGNORE_BOTS=false`) and have not run `/forget`.

Time is stored as individual **sessions** (`user`, `channel`, `start`, `end`)
rather than one running total. That is what makes time-windowed leaderboards
and the per-channel breakdown possible, and it means a leaderboard for "last
week" stays correct forever instead of being a snapshot.

Three things keep the data honest:

- **Reconciliation, not event replay.** Every voice event, every startup and a
  sweep every five minutes all funnel into the same comparison: *what session
  is open* vs. *what should be open*. Toggling your mic no longer restarts your
  clock, and switching channels no longer loses the first one.
- **Heartbeat-bounded crash recovery.** The bot writes a heartbeat every
  `RECONCILE_INTERVAL_SECONDS`. If it dies, sessions left open are closed at the
  last heartbeat on the next start — so an overnight outage credits nobody with
  eight hours they did not spend, and nobody loses their whole evening either.
  Worst case you lose one heartbeat interval.
- **Startup pickup.** Anyone already sitting in voice when the bot starts is
  picked up immediately. No rejoining required.

## Privacy

The bot stores Discord user IDs, channel IDs and session timestamps. It never
reads message content — it does not have the intent for it.

Any member can run `/export` to get their own data as a CSV, or `/forget` to
delete all of it and opt out of future tracking. `/forget` asks for
confirmation first. Server moderators can delete a member's data with
`/resetmember`.

The database is a single SQLite file; delete it to erase everything.

## Deployment

### systemd

```ini
# /etc/systemd/system/discordtimebot.service
[Unit]
Description=DiscordTimeBot
After=network-online.target

[Service]
Type=simple
User=discordtimebot
WorkingDirectory=/opt/DiscordTimeBot
EnvironmentFile=/opt/DiscordTimeBot/.env
ExecStart=/opt/DiscordTimeBot/.venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

`systemctl stop` sends `SIGTERM`, which closes open sessions cleanly before the
process exits, so no time is lost on a planned restart.

### Docker

```bash
docker build -t discordtimebot .
docker run -d --name discordtimebot \
  --env-file .env \
  -v "$PWD/data:/app/data" \
  --restart unless-stopped \
  discordtimebot
```

## Development

```bash
pip install -e ".[dev]"
pytest          # 83 tests, no network or Discord connection required
ruff check .
ruff format .
```

The tracking rules (`timebot/tracker.py`), the time windows
(`timebot/periods.py`) and the SQL (`timebot/storage.py`) are deliberately free
of discord.py types so they can be tested directly. `tests/test_tracking_cog.py`
drives the tracking cog with lightweight fakes and covers the scenarios that
historically went wrong: channel switching, muting, going AFK, deafening,
restarting with people already in voice, and disconnects that happened while
the bot was down.

### Project layout

```
main.py                     launcher (python main.py == python -m timebot)
timebot/
  bot.py                    bot class, extension loading, command sync
  config.py                 environment parsing and validation
  storage.py                SQLite layer: sessions, opt-outs, milestones
  tracker.py                "should this count?" rules, pure functions
  periods.py                today / week / month / year windows
  durations.py              duration parsing and formatting
  ui.py                     embed builders
  cogs/
    tracking.py             voice events, startup pickup, self-heal sweep
    leaderboard.py          /time /top /rank /stats /serverstats
    milestones.py           /milestones /syncroles + role granting
    data.py                 /export /forget /trackme /resetmember /botinfo
    digest.py               weekly recap loop + /digest
tests/                      83 tests
```

## Troubleshooting

**Slash commands don't show up.** Global commands can take up to an hour to
propagate. Set `GUILD_IDS` to your server ID for instant sync, and make sure
the bot was invited with the `applications.commands` scope.

**`PrivilegedIntentsRequired` on startup.** Enable *Server Members Intent* in
the Developer Portal (step 1 above).

**`PyNaCl is not installed, voice will NOT be supported`.** Harmless. The bot
observes voice state; it never joins a channel or handles audio.

**Milestone roles aren't granted.** Check that the bot has *Manage Roles* and
that its own role is above every milestone role in **Server Settings → Roles**.

## History

This started in 2020 as a single 200-line script for one server. That version
no longer runs: it imported its config with `from secrets.txt import TOKEN`,
which has never been valid Python, and it was written against discord.py 1.x
before intents, slash commands and `setup_hook` existed. It also used `/` as a
message prefix, which modern Discord clients intercept for slash commands.

Version 2.0 is a rewrite against discord.py 2.x. The original source is still
in the git history (`git show 76cfa0d:DiscordTimeBot.py`), and
[`CHANGELOG.md`](CHANGELOG.md) lists what was broken and what replaced it.

## License

[MIT](LICENSE).
