"""Service for handling image generation using Google Gemini (nano banana)."""

from typing import Optional
from loguru import logger
import os
from google import genai
from google.genai import types as genai_types
from pathlib import Path
from dotenv import load_dotenv
from config.image_uploader import UTFSUploader
import asyncio


# Load environment variables
load_dotenv()

GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"


class ImageService:
    """Service for handling image generation and processing."""

    def __init__(self):
        """Initialize the image service."""
        self.uploader = UTFSUploader(
            api_key=os.getenv("UTFS_KEY"),
            app_id=os.getenv("APP_ID")
        )
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=self.gemini_key) if self.gemini_key else None
        # Once generation fails with an auth error, stop trying for the life of
        # the process: every bot creation was firing a doomed Gemini call
        # (latency + ERROR spam) when the key was missing or expired.
        self.disabled = not self.gemini_key
        if self.disabled:
            logger.warning("GEMINI_API_KEY not set — persona image generation disabled")
        else:
            logger.info("Initialized Gemini client and UTFSUploader for image generation")

    async def generate_persona_image(
        self,
        name: str,
        prompt: str,
        style: str = "realistic",
        size: tuple[int, int] = (512, 512)
        ) -> Optional[str]:

        if self.disabled:
            logger.debug("Image generation disabled — skipping")
            return None

        try:
            # Add style to prompt. Gemini has no width/height/negative-prompt
            # knobs like SDXL — steer size and unwanted elements via text instead.
            full_prompt = (
                f"{style} style, {prompt}. "
                f"Square image, approximately {size[0]}x{size[1]} pixels. "
                "No text, no watermark, no logos, no signature."
            )

            logger.info(f"Generating image with prompt: {full_prompt}")

            # Generate image using Gemini (nano banana)
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=GEMINI_IMAGE_MODEL,
                contents=full_prompt,
                config=genai_types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )

            image_bytes = None
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    image_bytes = part.inline_data.data
                    break

            if not image_bytes:
                raise ValueError("No image data received from Gemini")

            # Save to temporary file
            temp_path = f"{name}.png"
            with open(temp_path, "wb") as f:
                f.write(image_bytes)

            # Upload to UTFS
            file_url = await asyncio.to_thread(self.uploader.upload_file, Path(temp_path))

            # Clean up temporary file
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                logger.warning(f"Temporary image file not found for cleanup: {temp_path}")

            if not file_url:
                raise ValueError("Failed to upload image to UTFS")

            return file_url
        
        except Exception as e:
            # Auth failures won't heal without a new key — disable for the rest
            # of the process so later bot creations skip generation instantly.
            error_text = str(e).lower()
            if "api key not valid" in error_text or "permission_denied" in error_text or "unauthenticated" in error_text:
                self.disabled = True
                logger.warning(
                    "Gemini rejected the API key — disabling persona image "
                    "generation until restart"
                )
            logger.error(f"Failed to generate image: {str(e)}")
            raise ValueError(f"Failed to generate image: {str(e)}") from e


# Create global instance
image_service = ImageService() 