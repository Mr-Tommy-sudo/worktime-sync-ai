"""
ai_parser.py — Интеграция с LLM для парсинга текста в структурированный JSON.

Поддерживаемые провайдеры:
    - Anthropic Claude (по умолчанию, через claude.ai API)
    - OpenAI / совместимые провайдеры (раскомментировать нужный блок)

Настройка:
    Задайте переменную окружения с API-ключом:
        export ANTHROPIC_API_KEY="sk-ant-..."   # для Claude
        export OPENAI_API_KEY="sk-..."          # для OpenAI

Использование:
    from ai_parser import parse_text_to_json
    result = parse_text_to_json("Работал над сайтом 3 часа")
    # → {"project_id": 1, "hours": 3.0, "raw_text": "Работал над сайтом 3 часа"}
"""

import json
import os
import requests
from typing import Optional


# ─── Конфигурация ─────────────────────────────────────────────────────────────

# Выберите провайдера: "anthropic" | "openai" | "gigachat" | "yandexgpt"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")

ANTHROPIC_API_KEY = "sk-ant-***"
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
GIGACHAT_TOKEN    = os.getenv("GIGACHAT_TOKEN", "")
YANDEX_API_KEY    = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID  = os.getenv("YANDEX_FOLDER_ID", "")

# Системный промпт по умолчанию
DEFAULT_SYSTEM_PROMPT = """Ты — помощник, который парсит свободный текст сотрудника о работе 
и возвращает СТРОГО JSON без лишнего текста.

Доступные проекты:
  1 — Редизайн сайта
  2 — CRM-интеграция
  3 — Мобильное приложение

Определи project_id (1, 2 или 3) и количество часов (дробное число).

Формат ответа (только JSON, ничего кроме JSON):
{"project_id": <int>, "hours": <float>, "raw_text": "<исходный текст>"}

Если проект определить невозможно, используй project_id: null.
Если часы определить невозможно, используй hours: null."""


# ─── Основная функция ─────────────────────────────────────────────────────────

def parse_text_to_json(
    user_text: str,
    system_prompt: Optional[str] = None,
    provider: Optional[str] = None,
) -> dict:
    """
    Отправляет текст в LLM и возвращает Python-словарь с распознанными данными.

    Args:
        user_text:     Свободный текст сотрудника, например "Работал над сайтом 3 часа".
        system_prompt: Кастомный системный промпт (опционально).
        provider:      Переопределить провайдера: "anthropic" | "openai" | "gigachat" | "yandexgpt".

    Returns:
        dict: {"project_id": int|None, "hours": float|None, "raw_text": str}

    Raises:
        ValueError:   Если LLM вернул невалидный JSON.
        RuntimeError: Если API-запрос завершился ошибкой.
    """
    if not user_text or not user_text.strip():
        raise ValueError("user_text не может быть пустым")

    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    active_provider = provider or LLM_PROVIDER

    try:
        if active_provider == "anthropic":
            raw_response = _call_anthropic(user_text, sys_prompt)
        elif active_provider == "openai":
            raw_response = _call_openai(user_text, sys_prompt)
        elif active_provider == "gigachat":
            raw_response = _call_gigachat(user_text, sys_prompt)
        elif active_provider == "yandexgpt":
            raw_response = _call_yandexgpt(user_text, sys_prompt)
        else:
            raise ValueError(f"Неизвестный провайдер: {active_provider}")

        return _parse_and_validate(raw_response, user_text)

    except (ValueError, RuntimeError):
        raise  # пробрасываем наши собственные ошибки как есть
    except Exception as exc:
        raise RuntimeError(f"Непредвиденная ошибка при обращении к LLM: {exc}") from exc


# ─── Парсинг и валидация ответа ───────────────────────────────────────────────

def _parse_and_validate(raw_response: str, original_text: str) -> dict:
    """Парсит строку ответа LLM в dict и проверяет обязательные поля."""
    if not raw_response or not raw_response.strip():
        raise ValueError("LLM вернул пустой ответ")

    # Иногда модели оборачивают JSON в ```json ... ``` — чистим
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        )

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM вернул невалидный JSON: {exc}\nОтвет модели: {raw_response[:300]}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"Ожидался dict, получен {type(data).__name__}")

    # Гарантируем наличие всех ожидаемых полей
    data.setdefault("project_id", None)
    data.setdefault("hours", None)
    data["raw_text"] = original_text  # всегда записываем исходный текст

    # Приводим типы
    if data["project_id"] is not None:
        data["project_id"] = int(data["project_id"])
    if data["hours"] is not None:
        data["hours"] = float(data["hours"])

    return data


# ─── Адаптеры для разных провайдеров ─────────────────────────────────────────

def _call_anthropic(user_text: str, system_prompt: str) -> str:
    """Запрос к Anthropic Claude API."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY не задан")

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 256,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_text}],
        },
        timeout=30,
    )
    _check_http_error(response, "Anthropic")
    return response.json()["content"][0]["text"]


def _call_openai(user_text: str, system_prompt: str) -> str:
    """Запрос к OpenAI API (или совместимому провайдеру)."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY не задан")

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text},
            ],
            "max_tokens": 256,
            "temperature": 0,
        },
        timeout=30,
    )
    _check_http_error(response, "OpenAI")
    return response.json()["choices"][0]["message"]["content"]


def _call_gigachat(user_text: str, system_prompt: str) -> str:
    """Запрос к GigaChat API (Сбер). Требует Bearer-токен."""
    if not GIGACHAT_TOKEN:
        raise RuntimeError("GIGACHAT_TOKEN не задан")

    response = requests.post(
        "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GIGACHAT_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "model": "GigaChat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text},
            ],
            "temperature": 0,
        },
        timeout=30,
        verify=False,  # GigaChat использует нестандартный CA
    )
    _check_http_error(response, "GigaChat")
    return response.json()["choices"][0]["message"]["content"]


def _call_yandexgpt(user_text: str, system_prompt: str) -> str:
    """Запрос к YandexGPT API."""
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        raise RuntimeError("YANDEX_API_KEY и YANDEX_FOLDER_ID должны быть заданы")

    response = requests.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        headers={
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
            "completionOptions": {"stream": False, "temperature": 0, "maxTokens": 256},
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user",   "text": user_text},
            ],
        },
        timeout=30,
    )
    _check_http_error(response, "YandexGPT")
    return response.json()["result"]["alternatives"][0]["message"]["text"]


def _check_http_error(response: requests.Response, provider_name: str) -> None:
    """Бросает RuntimeError с деталями, если HTTP-статус не 2xx."""
    if not response.ok:
        raise RuntimeError(
            f"{provider_name} API вернул ошибку {response.status_code}: {response.text[:300]}"
        )


# ─── Быстрый тест (запуск напрямую) ──────────────────────────────────────────

if __name__ == "__main__":
    test_phrases = [
        "Сегодня 4 часа занимался редизайном главной страницы",
        "Полдня потратил на настройку CRM — около 3.5 часов",
        "Утром 2 часа работал с API мобильного приложения",
    ]

    print(f"Провайдер: {LLM_PROVIDER}\n")
    for phrase in test_phrases:
        try:
            result = parse_text_to_json(phrase)
            print(f"  Вход:  {phrase}")
            print(f"  Выход: {result}\n")
        except (ValueError, RuntimeError) as e:
            print(f"  Ошибка для '{phrase}': {e}\n")
