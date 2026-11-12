"""Errors with a message that the bot can send to a user."""

from discord.ext import commands


class MusicError(commands.CommandError):
    """A music command could not complete."""
