import io
import functools
import logging
from typing import Optional, List, Coroutine, Any
import asyncio
import discord
from PIL import Image, ImageDraw, ImageFont

# Setup basic logging
logger = logging.getLogger('wolf_bot')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

@functools.lru_cache(maxsize=1)
def _get_default_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Gets default font. Cached to avoid repetitive disk I/O."""
    try:
        return ImageFont.load_default(size=80)
    except Exception:
         return ImageFont.load_default()

@functools.lru_cache(maxsize=20)
def _generate_number_image_bytes(number: int) -> bytes:
    """Generates an avatar with the specific number and caches the raw PNG bytes."""
    width, height = 200, 200
    image = Image.new('RGB', (width, height), color=(44, 47, 51))
    draw = ImageDraw.Draw(image)

    font = _get_default_font()
    text = str(number)

    # Calculate text bounding box to center it
    try:
        # Pillow >= 8.0.0
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
        # Older Pillow fallback
        text_width, text_height = draw.textsize(text, font=font)

    x = (width - text_width) / 2
    y = (height - text_height) / 2

    # Draw text
    draw.text((x, y), text, font=font, fill=(255, 255, 255))

    # Save to buffer
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def generate_number_image_file(number: int, filename: str = "number.png") -> discord.File:
    """Returns a discord.File object containing the generated number image."""
    image_bytes = _generate_number_image_bytes(number)
    return discord.File(io.BytesIO(image_bytes), filename=filename)

async def safe_send(user_or_channel: discord.abc.Messageable, *args, **kwargs) -> Optional[discord.Message]:
    """Safely sends a message, catching common exceptions."""
    try:
        return await user_or_channel.send(*args, **kwargs)
    except discord.Forbidden:
        logger.warning(f"Missing permissions to send message to {user_or_channel}")
    except discord.HTTPException as e:
        logger.error(f"Failed to send message: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending message: {e}")
    return None

async def gather_safe_sends(coroutines: List[Coroutine]) -> List[Any]:
    """Runs a list of send coroutines concurrently and handles exceptions."""
    return await asyncio.gather(*coroutines, return_exceptions=True)
