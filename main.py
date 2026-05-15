from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Импортируем твои функции из других файлов
from ai_parser import parse_text_to_json
from api_functions import get_all_projects

app = FastAPI()

# КРИТИЧЕСКИ ВАЖНО: Разрешаем браузеру (JS) общаться с нашим сервером
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Описываем, в каком формате ожидаем данные от JS
class ParseRequest(BaseModel):
    text: str

class SaveRequest(BaseModel):
    user_id: int
    project_id: int
    hours: float
    raw_text: str

# --- ЭНДПОИНТЫ (АДРЕСА) ---

@app.get("/api/projects")
def api_get_projects():
    # Отдаем список проектов из твоей базы
    return get_all_projects()

@app.post("/api/parse")
def api_parse_text(req: ParseRequest):
    # Отправляем текст в твой ai_parser
    result = parse_text_to_json(req.text)
    return result

@app.post("/api/save")
def api_save(req: SaveRequest):
    # Здесь ты потом подключишь свою функцию сохранения в БД
    # Например: save_time_log(req.user_id, req.project_id, req.hours, req.raw_text)
    print(f"Сохраняем в базу: Проект {req.project_id}, Часы: {req.hours}")
    return {"status": "ok"}