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
    for root, dirs, files in os.walk(cog_dir):
        # Skip hidden directories and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith("__") and not d.startswith(".")]
        
        # Get the package path
        package_path = root.replace("/", ".").replace("\\", ".")
        
        # Find Python files in this directory
        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                extension_path = f"{package_path}.{file[:-3]}"  # Remove the .py extension
                
                try:
                    await bot.load_extension(extension_path)
                    print(f"✅ Loaded extension: {extension_path}")
                    loaded_cogs += 1
                except Exception as e:
                    print(f"❌ Failed to load extension {extension_path}: {e}")
                    failed_cogs += 1
    
    # Load the voice cog separately since it's a package
    try:
        await bot.load_extension("cogs.voice")
        print(f"✅ Loaded extension: cogs.voice")
        loaded_cogs += 1
    except Exception as e:
        print(f"❌ Failed to load extension cogs.voice: {e}")
        failed_cogs += 1
    
    print(f"Extension loading complete. Loaded: {loaded_cogs}, Failed: {failed_cogs}")

async def main():
    bot = DiscordBot()
    await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == '__main__':
    asyncio.run(main())