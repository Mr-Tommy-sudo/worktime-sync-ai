"""Сервис интеграции с GigaChat API.

Документация: https://developers.sber.ru/docs/ru/gigachat/api/overview
- OAuth: POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth
- Chat:  POST https://gigachat.devices.sberbank.ru/api/v1/chat/completions
"""
import os
import time
import uuid
import logging
from typing import Optional

import requests
from dotenv import load_dotenv

# Загрузим .env из той же папки, где лежит этот файл
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

log = logging.getLogger("gigachat")
log.setLevel(logging.INFO)


class GigaChatNotConfigured(RuntimeError):
    """Поднимается, если в .env нет GIGACHAT_AUTH_KEY."""


class GigaChatError(RuntimeError):
    """Любая ошибка взаимодействия с API."""


class GigaChatClient:
    def __init__(self):
        self.auth_key = os.getenv("GIGACHAT_AUTH_KEY", "").strip()
        self.scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip()
        self.model = os.getenv("GIGACHAT_MODEL", "GigaChat").strip()
        verify_env = os.getenv("GIGACHAT_VERIFY_SSL", "false").strip().lower()
        self.verify_ssl = verify_env in ("1", "true", "yes")

        if not self.verify_ssl:
            # Глушим спам InsecureRequestWarning, когда verify=False
            try:
                from urllib3.exceptions import InsecureRequestWarning  # noqa: WPS433
                requests.packages.urllib3.disable_warnings(InsecureRequestWarning)  # noqa: SLF001
            except Exception:
                pass

        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.auth_key)

    # ---------- OAuth ----------
    def _get_token(self) -> str:
        if not self.configured:
            raise GigaChatNotConfigured("GIGACHAT_AUTH_KEY не задан в .env")

        # Если токен живой ещё хотя бы 60 секунд — отдаём из кэша
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        headers = {
            "Authorization": f"Basic {self.auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {"scope": self.scope}

        try:
            r = requests.post(
                OAUTH_URL, headers=headers, data=data,
                timeout=20, verify=self.verify_ssl,
            )
        except requests.RequestException as e:
            raise GigaChatError(f"Сбой при OAuth: {e}") from e

        if r.status_code != 200:
            raise GigaChatError(f"OAuth {r.status_code}: {r.text[:300]}")

        payload = r.json()
        self._token = payload["access_token"]
        # expires_at у Сбера приходит в миллисекундах, иногда — в секундах. На всякий нормализуем.
        expires_at_raw = payload.get("expires_at")
        if expires_at_raw and expires_at_raw > 10**12:
            self._token_expires_at = expires_at_raw / 1000.0
        elif expires_at_raw:
            self._token_expires_at = float(expires_at_raw)
        else:
            self._token_expires_at = time.time() + 25 * 60  # 25 минут по умолчанию

        return self._token

    # ---------- Chat ----------
    def chat(self, messages: list[dict], temperature: float = 0.4, max_tokens: int = 600) -> str:
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            r = requests.post(
                CHAT_URL, headers=headers, json=body,
                timeout=60, verify=self.verify_ssl,
            )
        except requests.RequestException as e:
            raise GigaChatError(f"Сбой при чат-инференсе: {e}") from e

        if r.status_code == 401:
            # Просрочили токен — сбросим кэш и попробуем ещё раз
            self._token = None
            token = self._get_token()
            headers["Authorization"] = f"Bearer {token}"
            r = requests.post(
                CHAT_URL, headers=headers, json=body,
                timeout=60, verify=self.verify_ssl,
            )

        if r.status_code != 200:
            raise GigaChatError(f"Chat {r.status_code}: {r.text[:300]}")

        data = r.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise GigaChatError(f"Не получилось распарсить ответ: {data}") from e

    def health(self) -> dict:
        """Проверка соединения: тянем токен. Возвращаем статус для UI."""
        if not self.configured:
            return {"configured": False, "online": False, "reason": "Ключ не задан"}
        try:
            self._get_token()
            return {"configured": True, "online": True, "model": self.model}
        except Exception as e:
            return {"configured": True, "online": False, "reason": str(e)}


# Singleton
client = GigaChatClient()


# ---------- Сборка system prompt из дашборда ----------
def build_system_prompt(team_payload: dict | None) -> str:
    base = (
        "Ты — AI Проджект-менеджер в системе WorkTime Sync. "
        "Отвечай только на русском языке, кратко и по делу. "
        "Анализируй текущее состояние команды, подсвечивай риски выгорания, "
        "конфликты в расписании, перегрузки и устаревшие графики. "
        "Если данные позволяют — предлагай конкретные действия (перенести встречу, "
        "снизить нагрузку, запросить подтверждение графика). "
        "Не выдумывай людей, которых нет в контексте."
    )
    if not team_payload:
        return base + "\n\nКонтекст команды не передан."

    lines = [base, "", f"Команда: {team_payload.get('team_name', '?')}", "Сотрудники:"]
    for m in team_payload.get("members_diagnostics", []):
        emp = m["employee"]
        mt = m["metrics"]
        # mt может быть pydantic-моделью или dict — нормализуем
        if hasattr(mt, "model_dump"):
            mt = mt.model_dump()
        elif hasattr(mt, "dict"):
            mt = mt.dict()
        task = emp.get("current_task") or "—"
        lines.append(
            f"- {emp['name']} ({emp.get('position','—')}, {emp['work_format']}, {emp['timezone']}) | "
            f"задача: {task} | загрузка {round(mt['load_level']*100)}%, "
            f"конфликты {round(mt['conflict_ratio']*100)}%, риск {mt['integrated_risk']:.2f} ({mt['risk_level']})"
        )
    windows = team_payload.get("best_meeting_times") or []
    if windows:
        lines.append("")
        lines.append("Ближайшие общие окна для встреч:")
        for w in windows:
            lines.append(f"  · {w}")
    return "\n".join(lines)
