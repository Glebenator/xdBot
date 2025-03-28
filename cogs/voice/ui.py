# cogs/voice/ui.py
import discord
from discord.ui import View, Button, button
import logging

logger = logging.getLogger(__name__)

class PlayerControls(View):
    """View with buttons to control the music player."""

    def __init__(self, player, cog, *, timeout=None):
        super().__init__(timeout=timeout)
        self.player = player
        self.cog = cog # Reference to the Voice cog if needed for invoking commands
        self.update_buttons() # Set initial state

    def update_buttons(self):
        """Updates button labels and styles based on player state."""
        # Pause/Resume Button
        pause_resume_button = discord.utils.get(self.children, custom_id="pause_resume")
        if pause_resume_button:
            if self.player.is_paused():
                pause_resume_button.label = "Resume ▶️"
                pause_resume_button.style = discord.ButtonStyle.green
            else:
                pause_resume_button.label = "Pause ⏸️"
                pause_resume_button.style = discord.ButtonStyle.secondary
            # Disable if not playing or paused
            pause_resume_button.disabled = not (self.player.is_playing() or self.player.is_paused())

        # Skip Button
        skip_button = discord.utils.get(self.children, custom_id="skip")
        if skip_button:
            skip_button.disabled = not self.player.current # Disable if nothing playing

        # Stop Button
        stop_button = discord.utils.get(self.children, custom_id="stop")
        if stop_button:
            stop_button.disabled = not self.player.current # Disable if nothing playing

        # Loop Button
        loop_button = discord.utils.get(self.children, custom_id="loop")
        if loop_button:
            if self.player.loop_mode == 'song':
                loop_button.label = "Loop: Song 🔂"
                loop_button.style = discord.ButtonStyle.primary
            elif self.player.loop_mode == 'queue':
                loop_button.label = "Loop: Queue 🔁"
                loop_button.style = discord.ButtonStyle.primary
            else: # off
                loop_button.label = "Loop: Off ➡️"
                loop_button.style = discord.ButtonStyle.secondary
            loop_button.disabled = False # Loop can always be toggled

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Allow only users in the same voice channel to interact."""
        if not interaction.user.voice or not interaction.guild.voice_client:
             await interaction.response.send_message("You need to be in the voice channel to use controls.", ephemeral=True)
             return False
        if interaction.user.voice.channel == interaction.guild.voice_client.channel:
            return True
        else:
             await interaction.response.send_message("You must be in the same voice channel as the bot.", ephemeral=True)
             return False

    async def on_timeout(self):
        """Disable all buttons when the view times out."""
        try:
             if self.message: # Check if message exists
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
        except discord.NotFound:
             pass # Ignore if message was deleted
        except Exception as e:
             logger.error(f"Error disabling controls on timeout: {e}")
        self.stop() # Stop the view listener

    # --- Button Callbacks ---

    @button(label="Pause ⏸️", style=discord.ButtonStyle.secondary, custom_id="pause_resume", row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: Button):
        """Toggles pause/resume state."""
        if self.player.is_paused():
            self.player.resume()
            await interaction.response.defer() # Acknowledge interaction
            # await interaction.followup.send("Resumed.", ephemeral=True) # Optional feedback
        elif self.player.is_playing():
            self.player.pause()
            await interaction.response.defer()
            # await interaction.followup.send("Paused.", ephemeral=True)
        else:
             await interaction.response.send_message("Nothing is playing.", ephemeral=True)
             return # Don't update buttons if nothing was playing

        self.update_buttons()
        await interaction.edit_original_response(view=self) # Update the message with new button state

    @button(label="Skip ⏭️", style=discord.ButtonStyle.primary, custom_id="skip", row=0)
    async def skip(self, interaction: discord.Interaction, button: Button):
        """Skips the current track."""
        if not self.player.current:
            await interaction.response.send_message("Nothing to skip.", ephemeral=True)
            return

        # Simple skip, no voting via buttons for now
        self.player.skip()
        await interaction.response.send_message(f"Track skipped by {interaction.user.mention}.", ephemeral=False)

        # Optionally disable buttons/view after skip?
        # button.disabled = True
        # await interaction.edit_original_response(view=self)
        # self.stop() # Stop view listener after skip if desired

    @button(label="Stop ⏹️", style=discord.ButtonStyle.danger, custom_id="stop", row=0)
    async def stop_playback(self, interaction: discord.Interaction, button: Button):
        """Stops playback and clears the queue."""
        self.player.clear_queue()
        if self.player.is_playing() or self.player.is_paused():
            self.player.stop_current() # Use a dedicated stop method if created

        await interaction.response.send_message(f"Playback stopped and queue cleared by {interaction.user.mention}.", ephemeral=False)
        # Disable all buttons after stopping
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
        self.stop() # Stop the view listener

    @button(label="Loop: Off ➡️", style=discord.ButtonStyle.secondary, custom_id="loop", row=1)
    async def toggle_loop(self, interaction: discord.Interaction, button: Button):
        """Cycles through loop modes."""
        if self.player.loop_mode == 'off':
            self.player.loop_mode = 'song'
            msg = "Loop mode set to: **Single Song** 🔂"
        elif self.player.loop_mode == 'song':
            self.player.loop_mode = 'queue'
            msg = "Loop mode set to: **Queue** 🔁"
        else:  # queue mode
            self.player.loop_mode = 'off'
            msg = "Loop mode set to: **Off** ➡️"

        self.update_buttons() # Update label/style
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(msg, ephemeral=True) # Send status update quietly

    @button(label="Shuffle 🔀", style=discord.ButtonStyle.secondary, custom_id="shuffle", row=1)
    async def shuffle_queue_button(self, interaction: discord.Interaction, button: Button):
         """Shuffles the queue."""
         if self.player.shuffle_queue():
             await interaction.response.send_message("Queue shuffled!", ephemeral=True)
         else:
             await interaction.response.send_message("Not enough songs in queue to shuffle.", ephemeral=True)