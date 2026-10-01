import io
import logging
from typing import Optional, Tuple
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("image_preprocessor")

_orientation_engine = None


def get_orientation_engine():
    """Lazily load the RapidOrientation model singleton."""
    global _orientation_engine
    if _orientation_engine is None:
        try:
            from rapid_orientation import RapidOrientation
            _orientation_engine = RapidOrientation()
            logger.info("Initialized RapidOrientation engine.")
        except Exception as exc:
            logger.warning("Failed to initialize RapidOrientation engine: %s", exc)
            _orientation_engine = False
    return _orientation_engine if _orientation_engine is not False else None


def normalize_image_orientation(file_bytes: bytes, mime_type: str) -> Tuple[bytes, str, Optional[int]]:
    """
    Detect and correct image rotation/orientation before passing to Gemini.
    
    Order of checks:
    1. Check EXIF orientation tag first; if present (> 1), transpose image.
    2. If EXIF is absent or already normal (tag == 1), use text-line-angle detection
       (RapidOrientation ONNX model) to detect 0, 90, 180, 270 degree rotation and auto-rotate to upright.
    
    Args:
        file_bytes: Raw bytes of the uploaded file.
        mime_type: File MIME type (e.g. 'image/jpeg', 'image/png').
        
    Returns:
        Tuple of (corrected_bytes, mime_type, rotation_applied_degrees).
        If no rotation was required, original file_bytes is returned and rotation_applied_degrees is 0.
    """
    if not mime_type.startswith("image/"):
        return file_bytes, mime_type, 0

    try:
        with io.BytesIO(file_bytes) as in_stream:
            img = Image.open(in_stream)
            img_format = img.format or ("PNG" if "png" in mime_type.lower() else "JPEG")
            
            # Step 1: Check EXIF orientation tag first
            exif = img.getexif()
            exif_orientation = exif.get(274) if exif else None
            
            if exif_orientation and exif_orientation > 1:
                logger.info("Found EXIF orientation tag %d. Transposing...", exif_orientation)
                transposed_img = ImageOps.exif_transpose(img)
                out_stream = io.BytesIO()
                # Save with high quality
                save_kwargs = {"quality": 95} if img_format.upper() in ["JPEG", "JPG"] else {}
                transposed_img.save(out_stream, format=img_format, **save_kwargs)
                corrected_bytes = out_stream.getvalue()
                return corrected_bytes, mime_type, int(exif_orientation)

            # Step 2: If EXIF is absent or already 1 (normal), use text-line-angle detection
            engine = get_orientation_engine()
            if engine is not None:
                # Convert PIL Image to RGB numpy array for orientation engine
                rgb_img = img.convert("RGB")
                img_np = np.array(rgb_img)
                # RapidOrientation expects BGR or RGB numpy array
                angle_str, elapse = engine(img_np)
                angle = int(angle_str)
                logger.info("RapidOrientation detected angle: %d° (inference time: %.3fs)", angle, elapse)
                
                if angle in [90, 180, 270]:
                    logger.info("Rotating image by %d° counter-clockwise to upright...", angle)
                    rotated_img = img.rotate(angle, expand=True)
                    out_stream = io.BytesIO()
                    save_kwargs = {"quality": 95} if img_format.upper() in ["JPEG", "JPG"] else {}
                    rotated_img.save(out_stream, format=img_format, **save_kwargs)
                    corrected_bytes = out_stream.getvalue()
                    return corrected_bytes, mime_type, angle

            # Step 3: No rotation needed
            return file_bytes, mime_type, 0

    except Exception as exc:
        logger.warning("Error during image orientation preprocessing: %s. Proceeding with original bytes.", exc)
        return file_bytes, mime_type, 0
