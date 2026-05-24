from typing import List, Dict
import models
import calculations

class AIAssistant:
    def __init__(self, employees: List[models.Employee], events_dict: Dict[int, List[models.Event]]):
        self.employees = employees
        self.events_dict = events_dict

    def generate_recommendations(self, employee: models.Employee) -> List[str]:
        """
        Генерация конкретных и объяснимых действий для улучшения планирования.
        """
        recs = []
        events = self.events_dict.get(employee.id, [])
        work_days = employee.work_days.split(",")
        
        # Получаем метрики для анализа
        days_unupdated = calculations.days_since_last_update(employee)
        conflict = calculations.conflict_ratio(employee, events, employee.work_start, employee.work_end, work_days)
        load = calculations.load_level(employee, events, employee.work_start, employee.work_end, work_days)
        
        # Правила рекомендаций на основе требований кейса
        if days_unupdated > 90:
            recs.append(f"Критично: График не обновлялся {days_unupdated} дней. Немедленно отправьте запрос на подтверждение.")
        elif days_unupdated > 30:
            recs.append("Попросить сотрудника подтвердить актуальность графика в системе.")
            
        if conflict > 0.2:
            recs.append("Выявлены регулярные встречи вне рабочего времени. Предложите перенести регулярную встречу или проверьте актуальность часового пояса.")
            
        if load > 0.8:
            recs.append("Сотрудник перегружен (высокая плотность встреч). Снизьте количество встреч на этой неделе и не назначайте новые крупные задачи.")
            
        if employee.work_format == "remote" and conflict > 0.3:
            recs.append("Возможно, сотрудник на удаленке сменил часовой пояс. Требуется уточнение данных у HR.")

        if not recs:
            recs.append("График выглядит актуальным, метрики в норме. Действий не требуется.")
            
        return recs

    def find_best_meeting_windows(self, team_id: int) -> List[str]:
        """
        Подбирает лучшее время для командных встреч.
        """
        # Отфильтруем сотрудников конкретной команды
        team_members = [emp for emp in self.employees if emp.team_id == team_id]
        if not team_members:
            return ["В команде нет сотрудников для поиска окон."]
            
        windows = calculations.team_common_windows(team_members, self.events_dict)
        
        if not windows:
            return ["На ближайшие дни нет общих окон, удовлетворяющих рабочим графикам всех участников."]
            
        return windows

    def answer_question(self, question: str, team_id: int = None) -> str:
        """
        Чат-ассистент: ответы на вопросы руководителя простым языком.
        """
        q = question.lower()
        
        team_members = self.employees
        if team_id:
            team_members = [emp for emp in self.employees if emp.team_id == team_id]

        # 1. Запрос по устаревшим графикам
        if "устарел" in q or "не обновлял" in q or "давно" in q:
            outdated = [emp.name for emp in team_members if calculations.days_since_last_update(emp) > 30]
            if outdated:
                return f"График скорее всего устарел у следующих сотрудников: {', '.join(outdated)}. Им стоит отправить запрос на обновление."
            return "У всех сотрудников в выбранной команде график относительно свежий (обновлялся менее 30 дней назад)."

        # 2. Запрос по перегрузкам
        if "перегружен" in q or "нагрузка" in q or "занят" in q:
            overloaded = []
            for emp in team_members:
                events = self.events_dict.get(emp.id, [])
                load = calculations.load_level(emp, events, emp.work_start, emp.work_end, emp.work_days.split(","))
                if load > 0.8:
                    overloaded.append(emp.name)
                    
            if overloaded:
                return f"Сейчас перегружены: {', '.join(overloaded)}. Рекомендую перенести часть их встреч."
            return "Никто из команды не превышает порог загрузки в 80%."

        # 3. Запрос на встречу
        if "встречу" in q or "когда" in q or "окно" in q or "собраться" in q:
            if not team_id:
                return "Пожалуйста, уточните команду (передайте team_id), чтобы я мог подобрать окна доступности."
            windows = self.find_best_meeting_windows(team_id)
            if "На ближайшие дни нет общих окон" in windows[0]:
                 return "К сожалению, общих окон для всей команды не найдено из-за конфликта часовых поясов или загруженности."
            return f"Вот лучшие окна для встречи команды: {', '.join(windows)}."
            
        # 4. Запрос по конфликтам
        if "конфликт" in q or "вне рабоче" in q:
            conflicted = []
            for emp in team_members:
                events = self.events_dict.get(emp.id, [])
                conflict = calculations.conflict_ratio(emp, events, emp.work_start, emp.work_end, emp.work_days.split(","))
                if conflict > 0.2:
                    conflicted.append(emp.name)
            if conflicted:
                return f"Частые встречи вне рабочего времени замечены у: {', '.join(conflicted)}."
            return "Критических конфликтов рабочего времени не обнаружено."

        # Fallback
        return ("Я — ИИ-ассистент WorkTime Sync. Я могу подсказать:\n"
                "- У кого устарел график?\n"
                "- Кто перегружен?\n"
                "- У кого есть конфликты в расписании?\n"
                "- Когда лучше провести командную встречу?")