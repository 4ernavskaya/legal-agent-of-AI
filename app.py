
from flask import Flask, render_template, request

from extractor import extract_text_from_image, extract_text_from_pdf

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # лимит 10 МБ

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    text = request.form.get("text", "").strip()
    file = request.files.get("document")
    has_file = file is not None and file.filename != ""

    if not text and not has_file:
        return render_template("index.html", error="Загрузите файл или вставьте текст документа."), 400

    if has_file:
        if not allowed_file(file.filename):
            return render_template("index.html", error="Поддерживаются только файлы PDF, JPG и PNG."), 400

        extension = file.filename.rsplit(".", 1)[1].lower()
        try:
            if extension == "pdf":
                document_text = extract_text_from_pdf(file.stream)
            else:
                document_text = extract_text_from_image(file.stream)
        except ValueError as e:
            return render_template("index.html", error=str(e)), 400
        source = file.filename
    else:
        document_text = text
        source = "вставленный текст"

    return render_template("result.html", source=source, document_text=document_text)


@app.errorhandler(413)
def file_too_large(error):
    return render_template("index.html", error="Файл слишком большой. Максимум 10 МБ."), 413


if __name__ == "__main__":
    app.run(debug=True)

