import re
import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger("captcha_solver")

# Lazy-loaded ddddocr instance
_ocr_instance = None
DDDDOCR_AVAILABLE = True

try:
    import ddddocr
except ImportError:
    DDDDOCR_AVAILABLE = False

try:
    from PIL import Image, ImageEnhance
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


def get_ocr_solver():
    global _ocr_instance
    if _ocr_instance is None and DDDDOCR_AVAILABLE:
        try:
            _ocr_instance = ddddocr.DdddOcr(show_ad=False)
        except Exception as e:
            logger.warning(f"Failed to initialize ddddocr: {e}")
            _ocr_instance = False
    return _ocr_instance if _ocr_instance is not False else None


def solve_image_captcha(image_bytes: bytes) -> Optional[str]:
    """
    Solves image-based CAPTCHA using ddddocr (primary, high accuracy)
    with fallback to PIL + Tesseract OCR.
    """
    if not image_bytes:
        return None

    # Method 1: ddddocr (recommended for India Post alphanumeric captchas)
    solver = get_ocr_solver()
    if solver is not None:
        try:
            raw_text = solver.classification(image_bytes)
            cleaned = re.sub(r'[^A-Za-z0-9]', '', raw_text).strip()
            if cleaned:
                logger.info(f"ddddocr solved captcha: '{cleaned}'")
                return cleaned
        except Exception as e:
            logger.warning(f"ddddocr failed: {e}")

    # Method 2: PIL + Tesseract fallback
    if TESSERACT_AVAILABLE:
        try:
            image = Image.open(BytesIO(image_bytes))
            gray = image.convert('L')
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(2.0)
            threshold = 140
            bw = enhanced.point(lambda p: 255 if p > threshold else 0)

            custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
            text = pytesseract.image_to_string(bw, config=custom_config).strip()
            cleaned = re.sub(r'[^A-Za-z0-9]', '', text)
            if cleaned:
                logger.info(f"Tesseract solved captcha: '{cleaned}'")
                return cleaned
        except Exception as e:
            logger.warning(f"Tesseract OCR fallback failed: {e}")

    logger.warning("No OCR solver succeeded for image captcha")
    return None


def solve_text_captcha(captcha_text: str) -> Optional[str]:
    """
    Parses legacy math expressions and textual captcha prompts from India Post form.
    """
    if not captcha_text:
        return None

    cleaned = captcha_text.strip().replace("=", "").strip()

    match = re.search(r'(\d+)\s*([\+\-\*])\s*(\d+)', cleaned)
    if match:
        num1 = int(match.group(1))
        op = match.group(2)
        num2 = int(match.group(3))

        if op == '+':
            ans = num1 + num2
        elif op == '-':
            ans = num1 - num2
        elif op == '*':
            ans = num1 * num2
        else:
            return None

        logger.info(f"Solved math captcha '{cleaned}' => {ans}")
        return str(ans)

    pos_match = re.search(r'(\d+)(?:st|nd|rd|th)\s+(?:character|number|digit)\s+(?:from|of)?\s*([A-Za-z0-9]+)', cleaned, re.IGNORECASE)
    if pos_match:
        pos = int(pos_match.group(1)) - 1
        seq = pos_match.group(2).strip()
        if 0 <= pos < len(seq):
            ans = seq[pos]
            logger.info(f"Solved position captcha '{cleaned}' => {ans}")
            return ans

    return None
