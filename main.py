# main.py
import os
import discord
from discord.ext import commands
import config
from dotenv import load_dotenv
import asyncio

# Load environment variables
load_dotenv()

class DiscordBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.PREFIX),
            intents=discord.Intents.all(),
            help_command=None  # We can create a custom help command later
        )
        
    async def setup_hook(self):
        await load_extensions(self)

    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        print(f'Bot is in {len(self.guilds)} guilds')
        
        # Set custom status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.streaming,
                name='xdd'
            )
        )

async def load_extensions(bot):
    """Load all extensions (cogs) from the cogs directory including subdirectories."""
    cog_dir = "cogs"  # Adjust if your cogs are in a different directory
    
    print(f"Loading extensions from {cog_dir}...")
    
    # Count loaded cogs for summary
    loaded_cogs = 0
    failed_cogs = 0
    
    # Walk through the cogs directory and load extensions
    for item in os.listdir(cog_dir):
        item_path = os.path.join(cog_dir, item)
        
        # Skip hidden files/folders and __pycache__
        if item.startswith("__") or item.startswith("."):
            continue
            
        extension_path = None
        
        # Case 1: Item is a Python file
        if os.path.isfile(item_path) and item.endswith('.py'):
            extension_path = f"{cog_dir}.{item[:-3]}"  # Remove the .py extension
            
        # Case 2: Item is a directory with an __init__.py file (module)
        elif os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
            extension_path = f"{cog_dir}.{item}"
        
        # Load the extension if it's valid
        if extension_path:
            try:
                await bot.load_extension(extension_path)
                print(f"✅ Loaded extension: {extension_path}")
                loaded_cogs += 1
            except Exception as e:
                print(f"❌ Failed to load extension {extension_path}: {e}")
                failed_cogs += 1
    
    print(f"Extension loading complete. Loaded: {loaded_cogs}, Failed: {failed_cogs}")

async def main():
    bot = DiscordBot()
    await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == '__main__':
    asyncio.run(main())