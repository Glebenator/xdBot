# main.py
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import config

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
        # Load all cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and filename != '__init__.py':
                await self.load_extension(f'cogs.{filename[:-3]}')
                print(f'Loaded cog: {filename[:-3]}')

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

def main():
    bot = DiscordBot()
    bot.run(os.getenv('DISCORD_TOKEN'))

if __name__ == '__main__':
    main()