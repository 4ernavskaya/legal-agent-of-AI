from flask import Flask, render_template, request
from extractor import extract_text_from_image, extract_text_from_pdf

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # лимит 10 МБ

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _render_error(message, status=400):
    return render_template("index.html", error=message), status


def _extract_document_text(file):
    """Достаёт текст из загруженного файла. Понятные пользователю ошибки приходят как ValueError."""
    extension = file.filename.rsplit(".", 1)[1].lower()
    if extension == "pdf":
        return extract_text_from_pdf(file.stream)
    return extract_text_from_image(file.stream)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    text = request.form.get("text", "").strip()
    file = request.files.get("document")
    has_file = file is not None and file.filename != ""

    if not text and not has_file:
        return _render_error("Загрузите файл или вставьте текст документа.")

    if not has_file:
        return render_template("result.html", source="вставленный текст", document_text=text)

    if not allowed_file(file.filename):
        return _render_error("Поддерживаются только файлы PDF, JPG и PNG.")

    try:
        document_text = _extract_document_text(file)
    except ValueError as error:
        return _render_error(str(error))
    else:
        return render_template("result.html", source=file.filename, document_text=document_text)


@app.errorhandler(413)
def file_too_large(error):
    return _render_error("Файл слишком большой. Максимум 10 МБ.", 413)


if __name__ == "__main__":
    app.run(debug=True, port=5001)