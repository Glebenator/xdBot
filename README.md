# xdBot

xdBot is a Discord bot with games, music, stock data, Quote Hall, auto-replies, and word tracking. Use a slash command or the `!` prefix.

## Deploy on a Linux server

GitHub Actions tests each change. A push to `botv2` also builds the image and checks that the bot, FFmpeg, and Deno start in it. GitHub Container Registry (GHCR) stores the tested image at `ghcr.io/glebenator/xdbot` with the tags `latest` and `sha-<full-commit-sha>`. The Linux service checks for an updated image every five minutes.

### First release

1. Push the release to `botv2`. Wait for **CI and image release** to complete in GitHub Actions.
2. Open the `xdbot` package settings in GitHub. Make the package public if the server must pull without credentials. For a private package, log in to GHCR on the server as root with a classic token that has `read:packages`. The systemd service uses root's Docker credentials.
3. Make sure the server has Docker Engine and the Docker Compose plugin. The published image uses Linux x86-64. Run the commands below from a copy of this repository on the server.

```sh
sudo install -d -m 0755 /opt/xdbot
sudo install -d -m 0750 -o 1000 -g 1000 /opt/xdbot/data
sudo install -m 0644 docker-compose.yml /opt/xdbot/docker-compose.yml
sudo install -m 0600 .env.example /opt/xdbot/.env
sudoedit /opt/xdbot/.env
```

Set `DISCORD_TOKEN` in `.env`. In the Discord Developer Portal, enable the **Message Content** and **Server Members** intents. Invite the bot with the `bot` and `applications.commands` scopes. Give it Connect and Speak permissions for music.

For an upgrade, stop the old bot before you copy its data. Save a backup of its complete `data/` directory. Copy its contents into `/opt/xdbot/data/` and give UID and GID 1000 access to the files. Use the old bot's token. Keep the backup until you confirm that the points, quotes, and other data are present in the new bot. The bot imports the old reply and word files as defaults for each server. Edits are stored in SQLite for that server.

4. Install the service and start it. It pulls the image before it replaces the container. Compose waits for the bot to connect to Discord.

```sh
sudo install -m 0644 deploy/xdbot-update.service deploy/xdbot-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start xdbot-update.service
sudo systemctl enable --now xdbot-update.timer
```

5. Check the update log and the bot log.

```sh
sudo journalctl -u xdbot-update.service -n 50 --no-pager
cd /opt/xdbot
sudo docker compose ps
sudo docker compose logs -f discord-bot
```

If Docker is installed at a different path, update both `ExecStart` lines in the service before you install it. To change the update schedule, edit the timer. To use an earlier refresh release, set `XDBOT_IMAGE=ghcr.io/glebenator/xdbot:sha-<full-commit-sha>` in `/opt/xdbot/.env` and start the service again. Remove the setting to resume updates to `latest`. If you return to an older database format, stop the bot and restore the backup first.

### Configuration

| Variable | Purpose |
| --- | --- |
| `DISCORD_TOKEN` | Required. Use the token for your Discord bot. |
| `BOT_PREFIX` | Prefix for text commands. The default is `!`. |
| `OWNER_IDS` | Optional. Comma-separated Discord user IDs for `reload` and `sync`. The application owner is the default. |
| `RANDOM_ORG_KEY` | Optional. Enables Random.org for the games. The bot uses local randomness when the service is unavailable. |
| `POLYGON_API_KEY` | Optional. Enables stock data from Massive. Existing Polygon API keys are valid. |
| `MUSIC_MAX_QUEUE_SIZE` | The default is 100 tracks. |
| `MUSIC_IDLE_TIMEOUT` | The default is 300 seconds. |
| `MUSIC_DEFAULT_VOLUME` | The default is 0.5. Use a value from 0 to 1. |
| `MUSIC_MAX_DURATION` | The default is 3,600 seconds. |

## Commands

| Area | Commands |
| --- | --- |
| Games | `успех`, `успехстат`, `топ`, `roll`, `огурчик`, `увлажнение`, `logitech`, `razer` |
| General | `help`, `ping` |
| Music | `join`, `play`, `pause`, `resume`, `skip`, `stop`, `volume`, `leave` |
| Quote Hall | `quote add`, `quote random`, `quote user`, `quote list`, `quote delete`. Use `!quote` or `/quote show` for a random quote. |
| Auto-replies | `listreplies`, `addreply`, `addreaction`, `removereply` |
| Word tracking | `addword`, `removeword`, `wordstats`, `wordleaderboard` |
| Stock data | `stock`, `stockinfo`, `stocksearch`, `marketstatus`, `stocknews`, `stockdividends`, `stocksplits`, `stockchart`, `stockcompare`, `stockrsi`, `stocksma`, `stockema`, `stockmacd`, `goldencross` |
| Points administration | `setpoints`, `addpoints`, `removepoints`, `setstreak`, `resetstats` |
| Bot owner | `!reload <cog>`, `!sync` |

`!успех` updates your points and streak once every 12 hours in each server. Music accepts recorded YouTube videos and search terms. Use the playback controls from the bot's voice channel. Saved Discord messages stay in their source channel or thread. Manual quotes are available across the server. Word statistics are sent privately to moderators.

## Run checks

Install Python 3.11 and create a virtual environment. FFmpeg and Deno are needed for local music playback. The Docker image includes both.

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
python main.py --check
python -m ruff check .
python -m pytest
```

`python main.py --check` loads the extensions with a temporary database and does not connect to Discord. The default test run skips tests that use external services. Run `python -m pytest -m integration` when you have the required services and credentials.

To run a local container build, create a local `.env` and run these commands.

```sh
docker build -t xdbot:dev .
XDBOT_IMAGE=xdbot:dev docker compose up -d --pull never
```
