import re
import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger("captcha_solver")

try:
    from PIL import Image, ImageEnhance, ImageFilter
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


def solve_text_captcha(captcha_text: str) -> Optional[str]:
    """
    Parses math expressions and textual captcha prompts from India Post form.
    Examples:
      - "Evaluate the Expression: 4 + 7 = "
      - "Evaluate the Expression: 9 - 3"
      - "What is 8 + 2"
    """
    if not captcha_text:
        return None

    cleaned = captcha_text.strip().replace("=", "").strip()

    # Match simple math expression: <num> <op> <num>
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

    # Match position query: "Enter the 3rd number from 94821" or "3rd character"
    pos_match = re.search(r'(\d+)(?:st|nd|rd|th)\s+(?:character|number|digit)\s+(?:from|of)?\s*([A-Za-z0-9]+)', cleaned, re.IGNORECASE)
    if pos_match:
        pos = int(pos_match.group(1)) - 1
        seq = pos_match.group(2).strip()
        if 0 <= pos < len(seq):
            ans = seq[pos]
            logger.info(f"Solved position captcha '{cleaned}' => {ans}")
            return ans

    return None


def solve_image_captcha(image_bytes: bytes) -> Optional[str]:
    """
    Solves image-based CAPTCHA using PIL preprocessing and Tesseract OCR.
    """
    if not TESSERACT_AVAILABLE:
        logger.warning("pytesseract/PIL not available for image captcha solving")
        return None

    try:
        image = Image.open(BytesIO(image_bytes))

        # Convert to grayscale
        gray = image.convert('L')

        # Increase contrast
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.0)

        # Apply slight thresholding to eliminate background noise
        threshold = 140
        bw = enhanced.point(lambda p: 255 if p > threshold else 0)

        # OCR with alphanumeric characters whitelist
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        text = pytesseract.image_to_string(bw, config=custom_config).strip()

        # Clean text
        text = re.sub(r'[^A-Za-z0-9]', '', text)
        if len(text) >= 4:
            logger.info(f"Image captcha solved: {text}")
            return text

    except Exception as e:
        logger.error(f"Image captcha OCR failed: {e}")

    return None
