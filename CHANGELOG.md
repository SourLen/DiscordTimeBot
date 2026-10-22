# Changelog

## 2.0.0 — rewrite for discord.py 2.x

The 2020 version did not run on any current Python or discord.py release. This
release rewrites it rather than patching it.

### Fixed — bot could not start at all

- **`from secrets.txt import GUILD, TOKEN`** is not valid as a module import.
  Python resolves it as the stdlib `secrets` module followed by a `txt`
  submodule, so starting the bot raised
  `ModuleNotFoundError: No module named 'secrets.txt'; 'secrets' is not a package`
  on the very first line. Replaced with environment variables and an optional
  `.env` file. The file name also shadowed the stdlib `secrets` module.

### Fixed — crashes and wrong numbers

- **`get(guild.voice_channels, name='Gulag').id` raised `AttributeError`** in
  any server without a channel called `Gulag`, on every single voice event. The
  AFK channel is now read from the server's own settings, and extra exclusions
  are configured by channel ID.
- **`if guild == GUILD` compared a `Guild` object to a string**, so it was never
  true and `/place`, `/top` and `/timeboard` all silently operated on whichever
  guild happened to be last in `client.guilds`.
- **`client.loop.create_task(checking())` was placed after `client.run(...)`**,
  which blocks until shutdown. The autosave task therefore never started, and
  on discord.py 2.x `client.loop` raises outside an async context anyway. All
  totals were lost on every restart. Background work now runs from
  `setup_hook` via `discord.ext.tasks`.
- **Nothing ever read `save.txt` back in**, and it stored a `repr()` of a dict
  keyed by `Member` objects, which is not loadable. Storage is now SQLite.
- **Members in voice when the bot started were invisible** until they moved
  channels. Startup now reconciles every voice channel.
- **Members who disconnected while the bot was down kept an open session**,
  which later turned into credit for the entire outage. Sessions left open are
  now closed at the last heartbeat.
- **Mute, deafen, camera and stream toggles fire `on_voice_state_update` too.**
  The old eight-branch `before`/`after` ladder treated some of them as a
  join or a leave. The bot now compares stored state against desired state in
  one place, so unrelated events are no-ops.
- **Switching channels** hit two branches of that ladder and could double count
  or drop the first channel's time.
- **`datetime.datetime.now()`** is naive local time and jumps with DST. All
  timestamps are now UTC Unix seconds.

### Fixed — unusable in modern Discord

- **`command_prefix='/'`** collides with Discord's slash-command UI; the client
  intercepts the message before the bot sees it. All commands are now real
  slash commands.
- **Prefix commands also require the Message Content intent** (privileged since
  August 2022). Slash commands do not, so the bot no longer requests it.
- **`discord.Intents.all()`** requested every privileged intent including
  presences, which the bot never used. The intent set is now `guilds`,
  `voice_states` and `members`.

### Fixed — behaviour and scale

- **`/top` sent one message per member**, which hits the channel rate limit
  almost immediately. Leaderboards are now a single embed.
- **`timeboard` was a byte-for-byte copy of `top`**, and the same 15-line
  leaderboard loop appeared three times. It now exists once, in SQL.
- **`place` and `top` mutated a module-level `leaderboard` dict and cleared it**
  mid-command, so two concurrent invocations corrupted each other's results.
- **`/place` silently returned nothing** when the member was not found.
- **The local variable `time` shadowed the `time` command** inside its own body.
- Placeholder output (`'no time amk'`) replaced with real responses.

### Added

- **Time-windowed leaderboards and stats** — today, this week, this month, this
  year, all time, resolved in a configurable IANA timezone.
- **Per-channel breakdown** in `/stats`, plus `/serverstats` for server-wide
  totals.
- **Milestone roles** — grant a role automatically when a member crosses a
  configured voice-time threshold (`MILESTONES=10h=Regular,100h=Veteran`),
  with `/milestones` to show progress and `/syncroles` to backfill.
- **Weekly digest** — a scheduled recap of last week's top 10 posted to a
  configured channel, with `/digest` to trigger it manually.
- **Data controls** — `/export` (CSV of your own sessions), `/forget` (delete
  everything and opt out, behind a confirmation button), `/trackme`,
  and `/resetmember` for moderators.
- **`/botinfo`** showing how the running instance is configured.
- **Multi-guild support** — the old code assumed a single hardcoded server.
- **Clean shutdown** — open sessions are flushed on `SIGTERM`.
- **83 tests**, ruff config, `pyproject.toml`, `.env.example`, `.gitignore`,
  a `Dockerfile` and a GitHub Actions workflow.

### Changed

- Single 200-line script → `timebot/` package with cogs.
- Totals-in-memory → sessions in SQLite with WAL.
- Hardcoded `GUILD` and `'Gulag'` → environment configuration.
