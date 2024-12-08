# Discord Bot

A versatile Discord bot built with discord.py that includes auto-replies, reactions, administrative commands, and fun features.

## Features

- Custom auto-replies with text and reactions
- Reaction-only triggers
- Administrative commands
- Fun commands
- Hybrid commands (supports both text and slash commands)

## Requirements

- Python 3.8 or higher
- Dependencies listed in `requirements.txt`
- Discord Bot Token
- Discord server with appropriate permissions

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd discord-bot
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory and add your Discord token:
```
DISCORD_TOKEN=your_token_here
```

4. Configure `config.py` with your settings:
```python
PREFIX = '!'  # Command prefix
OWNER_IDS = []  # Add your Discord user ID
GUILD_ID = None  # Optional: Add your guild ID for guild-specific commands
```

## Running the Bot

```bash
python main.py
```

## Commands

### General Commands
- `!help` - Display all available commands
- `!ping` - Check bot's latency

### Auto-Reply Commands
- `!addreply <trigger> [response] [reactions]` - Add new auto-reply with optional text and reactions
  - Example: `!addreply "hello" "Hi there!" "👋,😊"`
- `!addreaction <trigger> <reactions>` - Add reaction-only trigger
  - Example: `!addreaction "nice" "👍,🔥"`
- `!removereply <trigger>` - Remove an auto-reply trigger
- `!listreplies` - List all auto-reply triggers and responses

### Fun Commands
- `!roll [max_number]` - Roll a random number (default: 1-100)
  - Example: `!roll 20` - Roll between 1 and 20

### Admin Commands
- `!reload <extension>` - Reload a specific cog
- `!sync` - Sync slash commands

## Auto-Reply Features

The bot supports various types of auto-replies:

1. Text-only replies:
```
!addreply "hello" "Hi there!"
```

2. Reaction-only triggers:
```
!addreaction "nice" "👍,🔥"
```

3. Combined text and reactions:
```
!addreply "wow" "That's amazing!" "😮,🎉"
```

4. User mentions in replies:
```
!addreply "welcome" "Hello {user}! Welcome to the server!" "👋"
```
