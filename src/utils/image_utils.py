"""Image optimization utilities for faster AI vision analysis.

Resizes and compresses uploaded screenshots so the Copilot SDK vision model
processes them quickly instead of timing out on multi-MB originals.
"""

import io
import logging
from pathlib import Path

from PIL import Image

import config

logger = logging.getLogger(__name__)


def optimize_image(image_bytes: bytes, original_ext: str) -> tuple[bytes, str]:
    """Resize and compress an image for faster AI vision processing.

    Args:
        image_bytes: Raw image file bytes.
        original_ext: Original file extension (e.g. '.png', '.jpg').

    Returns:
        Tuple of (optimized_bytes, final_extension). The extension may change
        (e.g. GIF frames are kept as-is, but large PNGs may stay PNG).
    """
    ext = original_ext.lower()

    # Animated GIFs — skip optimization (Pillow can't reliably resize multi-frame)
    if ext == '.gif':
        return image_bytes, ext

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        logger.warning("Could not open image for optimization, keeping original")
        return image_bytes, ext

    original_size = len(image_bytes)
    max_dim = config.IMAGE_MAX_DIMENSION

    # --- Resize if exceeds max dimension ---
    w, h = img.size
    if w > max_dim or h > max_dim:
        ratio = min(max_dim / w, max_dim / h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        logger.info(f"Resized image from {w}x{h} to {new_w}x{new_h}")

    # --- Compress to buffer ---
    buf = io.BytesIO()

    if ext in ('.jpg', '.jpeg'):
        # Convert RGBA → RGB for JPEG
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(buf, format='JPEG', quality=config.IMAGE_JPEG_QUALITY, optimize=True)
        final_ext = ext
    elif ext == '.webp':
        img.save(buf, format='WEBP', quality=config.IMAGE_WEBP_QUALITY)
        final_ext = '.webp'
    else:
        # PNG and anything else
        if config.IMAGE_PNG_OPTIMIZE:
            img.save(buf, format='PNG', optimize=True)
        else:
            img.save(buf, format='PNG')
        final_ext = '.png'

    optimized = buf.getvalue()
    new_size = len(optimized)

    # Only use optimized version if it's actually smaller
    if new_size < original_size:
        savings_pct = (1 - new_size / original_size) * 100
        logger.info(
            f"Image optimized: {original_size:,} → {new_size:,} bytes "
            f"({savings_pct:.0f}% smaller)"
        )
        return optimized, final_ext
    else:
        logger.info(f"Image already optimal ({original_size:,} bytes), keeping original")
        return image_bytes, ext
