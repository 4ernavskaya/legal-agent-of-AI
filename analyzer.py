import json
import os
import re

from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.exceptions import GigaChatException

load_dotenv()

MODEL = "GigaChat-3-Ultra"
SCOPE = "GIGACHAT_API_PERS"
MAX_CHARS = 30000  # ограничение длины договора, потом уточним

# Какой CSS-класс соответствует уровню риска (для цвета карточки)
LEVELS = {"высокий": "high", "средний": "medium", "низкий": "low"}

INSTRUCTIONS = """Ты помощник, который объясняет договоры простым языком человеку без юридического образования.

Прочитай текст документа в конце и верни ТОЛЬКО JSON, без пояснений до и после и без markdown, в таком виде:
{
  "summary": "о чём документ, 2-4 предложения простыми словами",
  "obligations": [
    {"who": "кто обязан", "what": "что нужно сделать или оплатить", "deadline": "срок или размер, если указан"}
  ],
  "risks": [
    {"type": "вид риска", "level": "высокий, средний или низкий", "clause": "номер пункта или короткая цитата", "explanation": "чем это опасно, простыми словами"}
  ],
  "next_steps": ["что сделать дальше, например уточнить или обсудить с юристом"]
}

Правила:
- Используй только то, что написано в документе. Ничего не выдумывай. Если данных нет, пиши "не указано".
- Объясняй без юридических терминов, а если термин нужен, поясни его.
- В risks ищи: штрафы и неустойки, автоматическое продление, односторонний отказ или изменение условий, скрытые платежи, большую ответственность, невыгодную подсудность, сложное расторжение. Если рисков нет, верни пустой список.
- В next_steps обязательно напомни, что результат нужно проверить с юристом.

Текст документа:
"""


def ask_model(prompt):
    """Отправляет текст в GigaChat и возвращает ответ."""
    credentials = os.getenv("GIGACHAT_CREDENTIALS")
    if not credentials:
        raise ValueError("Не найден ключ GigaChat. Проверьте файл .env в корне проекта.")

    try:
        with GigaChat(
            credentials=credentials,
            scope=SCOPE,
            model=MODEL,
            verify_ssl_certs=False,
        ) as client:
            response = client.chat.create(prompt)
    except GigaChatException as exc:
        raise ValueError(f"Не удалось получить ответ от модели: {exc}") from exc
    else:
        return response.messages[0].content[0].text


def _parse_json(answer):
    """Достаёт JSON из ответа модели (она иногда оборачивает его в ```)."""
    cleaned = re.sub(r"```(?:json)?", "", answer).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Модель вернула ответ в неожиданном виде. Попробуйте ещё раз.")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("Не удалось разобрать ответ модели. Попробуйте ещё раз.") from exc


def analyze_document(document_text):
    """Главная функция: принимает текст договора, возвращает словарь с разбором."""
    if len(document_text) > MAX_CHARS:
        raise ValueError(f"Документ слишком длинный (больше {MAX_CHARS} символов).")

    answer = ask_model(INSTRUCTIONS + document_text)
    data = _parse_json(answer)

    risks = []
    for risk in data.get("risks", []):
        if isinstance(risk, dict):
            level = str(risk.get("level", "")).strip().lower()
            risk["css"] = LEVELS.get(level, "low")
            risks.append(risk)

    return {
        "summary": data.get("summary", "не указано"),
        "obligations": data.get("obligations", []),
        "risks": risks,
        "next_steps": data.get("next_steps", []),
    }