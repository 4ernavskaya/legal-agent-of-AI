import io
import logging
import os
import shutil

import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

logger = logging.getLogger(__name__)

OCR_LANG = "rus+eng"
MAX_OCR_PAGES = 10
RENDER_SCALE = 3

PDF_READ_ERROR = "Не удалось прочитать PDF: файл повреждён или имеет неподдерживаемый формат."
PDF_SCAN_ERROR = "Не удалось распознать скан: файл повреждён или имеет неподдерживаемый формат."

TESSERACT_CMD = ""
_TESSERACT_CANDIDATES = (
    r"D:\Games\tesseract.exe",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"D:\Games\Tesseract-OCR\tesseract.exe",
)
_TESSERACT_ERRORS = (pytesseract.TesseractError, pytesseract.TesseractNotFoundError)


def _safe_read_stream(file_stream):
    try:
        data = file_stream.read()
    except OSError as exc:
        raise ValueError("Не удалось прочитать загруженный файл.") from exc
    else:
        return data


def _safe_open_image(file_stream):
    try:
        image = Image.open(file_stream)
        image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError("Не удалось открыть изображение: файл повреждён или это не картинка.") from exc
    else:
        return image


def _safe_open_pdf(data):
    try:
        reader = PdfReader(io.BytesIO(data))
    except PyPdfError as exc:
        raise ValueError(PDF_READ_ERROR) from exc
    except Exception as exc:  # pypdf на битых файлах может бросить что угодно
        logger.exception("Неожиданная ошибка pypdf при открытии PDF")
        raise ValueError(PDF_READ_ERROR) from exc
    else:
        return reader


def _safe_extract_pdf_pages(reader):
    try:
        pages = [page.extract_text() or "" for page in reader.pages]
    except PyPdfError as exc:
        raise ValueError(PDF_READ_ERROR) from exc
    except Exception as exc:  # pypdf на битых файлах может бросить что угодно
        logger.exception("Неожиданная ошибка pypdf при извлечении текста")
        raise ValueError(PDF_READ_ERROR) from exc
    else:
        return pages


def _safe_open_pdfium(data):
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise ValueError(PDF_SCAN_ERROR) from exc
    else:
        return pdf


def _safe_render_page(pdf, index):
    try:
        bitmap = pdf[index].render(scale=RENDER_SCALE)
        image = bitmap.to_pil()
    except pdfium.PdfiumError as exc:
        raise ValueError(PDF_SCAN_ERROR) from exc
    else:
        return image


def _safe_get_installed_languages():
    try:
        languages = pytesseract.get_languages(config="")
    except _TESSERACT_ERRORS as exc:
        logger.exception("Не удалось получить список языков Tesseract")
        raise ValueError("Не удалось запустить Tesseract OCR. Проверьте, что он установлен корректно.") from exc
    else:
        return set(languages)


def _safe_image_to_string(image):
    try:
        text = pytesseract.image_to_string(image, lang=OCR_LANG)
    except _TESSERACT_ERRORS as exc:
        logger.exception("Tesseract не смог обработать изображение")
        raise ValueError("Не удалось распознать текст: ошибка Tesseract OCR.") from exc
    else:
        return text



def _find_tesseract():
    """Ищет путь к tesseract: ручная настройка, PATH, типовые места установки."""
    if TESSERACT_CMD and os.path.exists(TESSERACT_CMD):
        return TESSERACT_CMD

    path = shutil.which("tesseract")
    if path:
        return path

    for candidate in _TESSERACT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


TESSERACT_PATH = _find_tesseract()
if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def _check_ocr_ready():
    """Проверяет, что Tesseract установлен и в нём есть нужные языки."""
    if not TESSERACT_PATH:
        raise ValueError(
            "Не найдена программа Tesseract OCR. Установите её (инструкция в README) "
            "и перезапустите сайт."
        )

    installed = _safe_get_installed_languages()
    missing = [lang for lang in OCR_LANG.split("+") if lang not in installed]
    if missing:
        raise ValueError(
            "В Tesseract не установлен язык: " + ", ".join(missing) + ". "
            "Переустановите Tesseract и отметьте нужный язык в разделе Additional language data."
        )




def _ocr_image(image):
    """Распознаёт текст на картинке."""
    _check_ocr_ready()
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    return _safe_image_to_string(image)


def extract_text_from_image(file_stream):
    """Достаёт текст из фото документа (JPG/PNG) через OCR."""
    image = _safe_open_image(file_stream)

    text = _ocr_image(image).strip()
    if not text:
        raise ValueError(
            "Не удалось распознать текст на фото. Попробуйте более чёткий снимок: "
            "хорошее освещение, документ без наклона и бликов."
        )
    return text


def _ocr_pdf_pages(data):
    """Распознаёт текст в PDF-скане постранично (не больше MAX_OCR_PAGES страниц)."""
    pdf = _safe_open_pdfium(data)
    try:
        page_count = min(len(pdf), MAX_OCR_PAGES)
        texts = [_ocr_image(_safe_render_page(pdf, index)) for index in range(page_count)]
    finally:
        pdf.close()
    return "\n".join(texts).strip()


def extract_text_from_pdf(file_stream):
    """Достаёт текст из PDF: сначала из текстового слоя, если его нет — через OCR."""
    data = _safe_read_stream(file_stream)

    reader = _safe_open_pdf(data)
    if reader.is_encrypted:
        raise ValueError("PDF защищён паролем. Загрузите файл без пароля.")

    text = "\n".join(_safe_extract_pdf_pages(reader)).strip()
    if text:
        return text

    text = _ocr_pdf_pages(data)
    if not text:
        raise ValueError("Не удалось распознать текст в скане. Попробуйте файл лучшего качества.")
    return text