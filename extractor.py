import io
import os
import shutil

import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader

OCR_LANG = "rus+eng"
MAX_OCR_PAGES = 10
RENDER_SCALE = 3


TESSERACT_CMD = ""


def _find_tesseract():

    if TESSERACT_CMD and os.path.exists(TESSERACT_CMD):
        return TESSERACT_CMD
    path = shutil.which("tesseract")
    if path:
        return path
    for candidate in (
            r"D:\Games\tesseract.exe",
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"D:\Games\Tesseract-OCR\tesseract.exe",
            r"D:\Games\tesseract.exe",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


TESSERACT_PATH = _find_tesseract()
if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def _check_ocr_ready():
    """Проверяет, что Tesseract установлен и в нём есть все нужные языки."""
    if not TESSERACT_PATH:
        raise ValueError(
            "Не найдена программа Tesseract OCR. Установите её (инструкция в README) "
            "и перезапустите сайт."
        )
    installed = set(pytesseract.get_languages(config=""))
    missing = [lang for lang in OCR_LANG.split("+") if lang not in installed]
    if missing:
        raise ValueError(
            "В Tesseract не установлен язык: " + ", ".join(missing) + ". "
                                                                      "Переустановите Tesseract и отметьте нужный язык в разделе Additional language data."
        )


def _ocr_image(image):

    _check_ocr_ready()
    image = ImageOps.exif_transpose(image)  # учитываем поворот, записанный камерой телефона
    image = image.convert("L")  # чёрно-белое изображение распознаётся лучше
    return pytesseract.image_to_string(image, lang=OCR_LANG)


def extract_text_from_image(file_stream):

    try:
        image = Image.open(file_stream)
        image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise ValueError("Не удалось открыть изображение: файл повреждён или это не картинка.")

    text = _ocr_image(image).strip()
    if not text:
        raise ValueError(
            "Не удалось распознать текст на фото. Попробуйте более чёткий снимок: "
            "хорошее освещение, документ без наклона и бликов."
        )
    return text


def _ocr_pdf_pages(data):

    pdf = pdfium.PdfDocument(data)
    try:
        page_count = min(len(pdf), MAX_OCR_PAGES)
        texts = []
        for index in range(page_count):
            bitmap = pdf[index].render(scale=RENDER_SCALE)
            texts.append(_ocr_image(bitmap.to_pil()))
        return "\n".join(texts).strip()
    finally:
        pdf.close()


def extract_text_from_pdf(file_stream):

    data = file_stream.read()

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("PDF защищён паролем. Загрузите файл без пароля.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ValueError:
        raise
    except Exception:
        raise ValueError("Не удалось прочитать PDF: файл повреждён или имеет неподдерживаемый формат.")

    text = "\n".join(pages).strip()
    if text:
        return text


    try:
        text = _ocr_pdf_pages(data)
    except ValueError:
        raise
    except Exception:
        raise ValueError("Не удалось распознать скан: файл повреждён или имеет неподдерживаемый формат.")

    if not text:
        raise ValueError("Не удалось распознать текст в скане. Попробуйте файл лучшего качества.")
    return text

