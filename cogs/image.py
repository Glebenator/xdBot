# cogs/image.py
import discord
from discord.ext import commands
import cv2
import numpy as np
import mediapipe as mp
import tempfile
import os
from utils.helpers import create_embed

class ImageProcessing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Initialize MediaPipe Face Mesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=10,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )

    def get_eye_coordinates(self, image, face_landmarks):
        """Extract eye coordinates from MediaPipe face landmarks"""
        image_height, image_width = image.shape[:2]
        
        # MediaPipe indices for eyes
        LEFT_EYE_INDICES = [33, 133, 160, 159, 158, 157, 173]  # Left eye landmarks
        RIGHT_EYE_INDICES = [362, 263, 387, 386, 385, 384, 398]  # Right eye landmarks
        
        # Get coordinates for both eyes
        eyes = []
        for eye_indices in [LEFT_EYE_INDICES, RIGHT_EYE_INDICES]:
            points = []
            for idx in eye_indices:
                landmark = face_landmarks.landmark[idx]
                x = int(landmark.x * image_width)
                y = int(landmark.y * image_height)
                points.append((x, y))
            
            # Calculate eye center and size
            points = np.array(points)
            center = np.mean(points, axis=0).astype(int)
            
            # Calculate eye width for radius
            left_point = points[0]
            right_point = points[3]
            eye_width = np.linalg.norm(np.array(left_point) - np.array(right_point))
            radius = int(eye_width / 2)
            
            eyes.append((center, radius))
        
        return eyes

    def apply_demonic_effects(self, img, eyes):
        """Apply demonic effects to the eyes"""
        # Create separate layers for glow and streaks
        glow_layer = np.zeros_like(img)
        streak_layer = np.zeros_like(img)
        
        # Draw glowing red eyes and white streaks
        for center, radius in eyes:
            # Create smaller, more focused red glow
            for r in range(radius + 10, radius - 3, -1):
                intensity = int(255 * (1 - (r - radius + 3) / 13))
                cv2.circle(glow_layer, tuple(center), r, (0, 0, intensity), -1)
            
            # Add bright center
            cv2.circle(glow_layer, tuple(center), radius - 3, (0, 0, 255), -1)
        
        # Apply different Gaussian blurs for glow and streaks
        glow_layer = cv2.GaussianBlur(glow_layer, (15, 15), 7)
        
        # Blend everything together
        img = cv2.addWeighted(img, 1, glow_layer, 0.7, 0)
        
        return img

    @commands.hybrid_command(
        name="deamonify",
        description="Detect eyes and make them glow demonically"
    )
    async def find_eyes(self, ctx: commands.Context):
        """
        Detect eyes in an attached image and apply demonic effects
        """
        if not ctx.message.attachments:
            await ctx.send("Please attach an image!")
            return

        attachment = ctx.message.attachments[0]
        
        # Check if the attachment is an image
        if not any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
            await ctx.send("Please provide a valid image file (PNG, JPG, JPEG, or WEBP)!")
            return

        await ctx.defer()  # Defer response since image processing might take time

        try:
            # Download the image
            image_data = await attachment.read()
            image_array = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            if img is None:
                await ctx.send("Failed to process the image!")
                return

            # Convert BGR to RGB for MediaPipe
            rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Detect face landmarks
            results = self.face_mesh.process(rgb_image)
            
            if not results.multi_face_landmarks:
                await ctx.send("No faces detected in the image!")
                return

            # Get eye coordinates for all faces
            all_eyes = []
            for face_landmarks in results.multi_face_landmarks:
                eyes = self.get_eye_coordinates(img, face_landmarks)
                all_eyes.extend(eyes)

            if not all_eyes:
                await ctx.send("No eyes detected in the image!")
                return

            # Apply demonic effects
            processed_img = self.apply_demonic_effects(img, all_eyes)

            # Save the processed image
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                cv2.imwrite(tmp_file.name, processed_img)
                
                # Create embed
                embed = create_embed(
                    title="👿 Demonic Eye Transformation",
                    color=discord.Color.red().value
                )

                # Send the processed image
                await ctx.send(
                    embed=embed,
                    file=discord.File(tmp_file.name, 'processed_image.png')
                )

            # Clean up temporary file
            os.unlink(tmp_file.name)

        except Exception as e:
            error_embed = create_embed(
                title="Error",
                description=f"Failed to process image: {str(e)}",
                color=discord.Color.red().value
            )
            await ctx.send(embed=error_embed)

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        self.face_mesh.close()

async def setup(bot):
    await bot.add_cog(ImageProcessing(bot))