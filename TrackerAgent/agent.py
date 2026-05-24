import pygetwindow as gw
import time
import requests

# Настройки
BACKEND_URL = "http://127.0.0.1:8000/api/activity"
USER_ID = 1 # ID текущего сотрудника
POLL_INTERVAL = 5 # Проверять каждые 5 секунд

def format_duration(total_seconds: int) -> str:
    """Умная функция для перевода секунд в часы, минуты и секунды с правильными окончаниями"""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    # Функция для правильного склонения слов в русском языке
    def pluralize(value, word1, word2, word5):
        if value % 10 == 1 and value % 100 != 11:
            return f"{value} {word1}"
        elif 2 <= value % 10 <= 4 and (value % 100 < 10 or value % 100 >= 20):
            return f"{value} {word2}"
        else:
            return f"{value} {word5}"

    parts = []
    if hours > 0:
        parts.append(pluralize(hours, "час", "часа", "часов"))
    if minutes > 0:
        parts.append(pluralize(minutes, "минута", "минуты", "минут"))
    if seconds > 0 or total_seconds == 0:
        parts.append(pluralize(seconds, "секунда", "секунды", "секунд"))
        
    return " ".join(parts)


def start_tracking():
    print("Агент запущен! Сворачивай окно и работай, я слежу за тобой 👀")
    
    current_window = None
    start_time = time.time()

    while True:
        try:
            active_window = gw.getActiveWindow()
            window_title = active_window.title if active_window else "Неизвестно"
            
            if window_title != current_window:
                if current_window is not None:
                    duration = int(time.time() - start_time)
                    if duration > 0:
                        # В Бэкенд отправляем сырые СЕКУНДЫ (duration), это важно для математики!
                        data = {
                            "user_id": USER_ID,
                            "app_name": current_window.split("-")[-1].strip(),
                            "window_title": current_window,
                            "duration_seconds": duration
                        }
                        try:
                            requests.post(BACKEND_URL, json=data)
                            # А вот в консоль выводим красоту:
                            readable_time = format_duration(duration)
                            print(f"Отправлено: {readable_time} в '{current_window}'")
                        except Exception as e:
                            print("Ошибка связи с сервером")

                current_window = window_title
                start_time = time.time()
                
            time.sleep(POLL_INTERVAL)
            
        except Exception as e:
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    start_tracking()