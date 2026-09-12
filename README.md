# krillion-bot

A small Discord bot for groups that play [Krillion.io](https://krillion.io) daily.
Paste your result in Discord, the bot records it, posts a leaderboard when the
puzzle closes and keeps an Elo rating for everyone.

```
Krillion #58 🦐
340

🦑🦑🦑🦑🦑🐟🫧
```

Designed to run on an Oracle Cloud *Always Free* VM: one Python process,
SQLite on disk, ~60 MB RAM, no other services.

## What it does

- **Reads results** from any message containing `Krillion #<n>` followed by the
  score. Reacts 🦐 when recorded. The puzzle number must be the one that is
  live right now (Krillion rolls over at midnight New York = **2pm AEST**, or
  3pm AEST while the US is on standard time). Old / future numbers are refused
  with a short reply; a second paste for the same puzzle keeps the first score.
- **Grace period**: results for the puzzle that just closed are still accepted
  for `LATE_GRACE_MINUTES` (default 10) after the reset, so a paste at 2:03pm
  isn't lost.
- **Daily leaderboard**: once the grace period ends the bot posts the final
  standings for that puzzle with each player's Elo change. It is posted to
  `LEADERBOARD_CHANNEL_ID`, or to the channel the results were shared in.
  Days missed while the bot was offline are closed out on the next start.
- **Elo**: everyone starts at **1200**. Each day every submitter is scored
  against every other submitter (win / draw / loss by score). K is 32, split
  across opponents, so a day can move you at most ±32 and the size of the
  change depends on who else played and how strong they are. A day with a
  single submitter changes nothing.
- **Provisional ratings**: a player's first 5 rated days use K = 64 (max
  ±64/day) so new divers reach their real level fast. They're shown with a
  `?` after the rating (e.g. `1264?`) until established.
- **Slash commands**
  - `/leaderboard [puzzle]` – live scores for today (or the final table for a
    past puzzle number)
  - `/elo` – Elo rankings
  - `/stats [member]` – rating, games, wins, best and average score
  - `/puzzle` – which puzzle is live and when it resets (shown in each user's
    local time)
  - `/invalidate <member> [puzzle] [reason]` – **admins only**: remove a
    misreported score. If the day is still open the player can repost; if it
    was already closed, every closed day's Elo is replayed from the remaining
    results so ratings stay consistent.
- **Admins** are the Discord user IDs in `ADMIN_USER_IDS` (default:
  `750888871696269402`).

## 1. Create the Discord application

1. <https://discord.com/developers/applications> → **New Application**.
2. **Bot** tab → *Reset Token* → copy it (this is `DISCORD_TOKEN`).
3. Still on **Bot**, under *Privileged Gateway Intents* enable
   **Message Content Intent** (required to read pasted results).
4. **OAuth2 → URL Generator**: scope `bot` + `applications.commands`;
   bot permissions *View Channels*, *Send Messages*, *Read Message History*,
   *Add Reactions*. Open the generated URL and add the bot to your server.

## 2. Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env            # put DISCORD_TOKEN in here
.venv/bin/python -m pytest      # tests
.venv/bin/python -m krillion_bot
```

Slash commands are synced on startup; Discord can take a few minutes to show
them the first time.

## 3. Host it on an Oracle Always Free VM

Any free-tier shape works (the `VM.Standard.E2.1.Micro` with 1 GB RAM is
plenty; an Ampere `A1.Flex` is fine too). Use the **Canonical Ubuntu** image
when creating the instance — Oracle Linux also works (`dnf` path). No ingress
ports need to be opened; the bot only makes outbound connections to Discord.

From your machine, with `.env` filled in:

```bash
./deploy/deploy.sh ubuntu@<vm-public-ip> ~/.ssh/<your-oracle-key>
# or:  make deploy HOST=ubuntu@<vm-public-ip> KEY=~/.ssh/<your-oracle-key>
```

(Use `opc@` instead of `ubuntu@` on an Oracle Linux image.)

The script copies the repo to `~/krillion-bot` on the VM, seeds `.env` from
your local one (only if the VM doesn't already have one), adds a 2 GB swapfile
if the VM has none, installs Python and the dependencies into a venv, installs
a hardened `systemd` service (`deploy/krillion-bot.service`) and starts it.
Re-run the same command to deploy updates — the database in
`~/krillion-bot/data/` is untouched.

The 1 GB micro shape is slow: the first run can take 5–10 minutes while the
package manager works (later runs skip it). If the VM stops answering ssh
during a first deploy it has run out of memory — reboot it from the Oracle
console and re-run the deploy; the swapfile is created before anything heavy
runs so it won't happen twice.

On the VM:

```bash
sudo journalctl -u krillion-bot -f        # logs
sudo systemctl restart krillion-bot       # restart
sudo systemctl status krillion-bot
nano ~/krillion-bot/.env                  # change config, then restart
```

If you didn't have a local `.env`, ssh in, edit `~/krillion-bot/.env`, set
`DISCORD_TOKEN`, and `sudo systemctl restart krillion-bot`.

## Configuration

All settings live in `.env` (see `.env.example`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `DISCORD_TOKEN` | – | Bot token (required) |
| `LEADERBOARD_CHANNEL_ID` | empty | Channel for the daily post; empty = where results were shared |
| `RESULTS_CHANNEL_ID` | empty | Only read results from this channel; empty = all channels |
| `DATABASE_PATH` | `data/krillion.sqlite3` | SQLite file |
| `LATE_GRACE_MINUTES` | `10` | How long after reset the previous puzzle is still accepted |
| `ELO_K` | `32` | Elo K-factor (max daily swing) |
| `ELO_PROVISIONAL_K` | `64` | K-factor during a player's provisional period |
| `ELO_PROVISIONAL_GAMES` | `5` | Rated days before a player is established |
| `ADMIN_USER_IDS` | `750888871696269402` | Comma-separated user IDs allowed to run admin commands |
| `KRILLION_TIMEZONE` | `America/New_York` | Timezone the game resets in |
| `KRILLION_EPOCH_DATE` | `2026-07-16` | Date of Krillion #1 |

The last two mirror how krillion.io numbers its puzzles; only change them if
the game changes.

## Layout

```
krillion_bot/
  parser.py      share-text parser
  puzzle.py      puzzle number <-> date, reset times
  elo.py         multiplayer Elo
  storage.py     SQLite persistence
  service.py     submissions, grace period, closing a day
  formatting.py  leaderboard text
  bot.py         Discord glue (events, scheduler, slash commands)
deploy/          deploy.sh, setup-vm.sh, systemd unit
tests/
```
