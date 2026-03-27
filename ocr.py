# ======================================
# OCR MODULE FOR AI TRADER SIGNAL SYSTEM
# ======================================

from PIL import Image
import pytesseract

# Set Tesseract path for Windows (adjust if needed)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_text_from_image(image):
    """
    Accepts a PIL image object and returns the extracted text using OCR.
    """
    return pytesseract.image_to_string(image)
