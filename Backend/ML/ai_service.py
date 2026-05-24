import json
from gigachat import GigaChat

# ВСТАВЬ СВОИ АВТОРИЗАЦИОННЫЕ ДАННЫЕ (КЛЮЧ) ОТ GIGACHAT СЮДА:
GIGACHAT_CREDENTIALS = "твой_длинный_ключ_от_сбера"

def extract_time_and_project(user_text: str) -> dict:
    if GIGACHAT_CREDENTIALS and GIGACHAT_CREDENTIALS != "твой_длинный_ключ_от_сбера":
        try:
            prompt = f"""
            Ты - строгий HR-ассистент. Прочитай текст сотрудника и вытащи оттуда потраченное время в часах (числом) и ID проекта.
            Список проектов (ID): 
            1 - Редизайн сайта
            2 - CRM-интеграция
            3 - Мобильное приложение
            
            Текст сотрудника: "{user_text}"
            
            Верни ТОЛЬКО валидный JSON без лишних слов. Пример: {{"project_id": 1, "hours": 4.5}}
            """

            with GigaChat(credentials=GIGACHAT_CREDENTIALS, verify_ssl_certs=False) as giga:
                response = giga.chat({
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                })
                
                ai_answer = response.choices[0].message.content
                
                # --- УМНЫЙ ПАРСЕР ---
                # Ищем, где начинается первая скобка '{' и заканчивается последняя '}'
                start_idx = ai_answer.find('{')
                end_idx = ai_answer.rfind('}')
                
                if start_idx != -1 and end_idx != -1:
                    clean_json = ai_answer[start_idx:end_idx+1]
                    return json.loads(clean_json)
                else:
                    raise ValueError(f"Не нашел JSON в ответе. Ответ был: {ai_answer}")
                
        except Exception as e:
            print(f"Ошибка GigaChat: {e}. Переключаемся на заглушку!")

    # --- РЕЗЕРВНАЯ ЗАГЛУШКА ---
    print("Используем локальную заглушку")
    hours = 4.0 
    words = user_text.split()
    for word in words:
        if word.isdigit():
            hours = float(word)
            break
            
    project_id = 1
    lower_text = user_text.lower()
    if "crm" in lower_text or "баз" in lower_text:
        project_id = 2
    elif "мобил" in lower_text or "приложен" in lower_text:
        project_id = 3

    return {
        "project_id": project_id,
        "hours": hours
    }