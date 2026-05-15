// 1. Конфигурация
const API_BASE_URL = 'http://localhost:8000/api'; // Адрес бэкенда FastAPI
const CURRENT_USER_ID = 1; 
let originalText = "";

// 2. Инициализация и привязка событий при загрузке страницы
document.addEventListener("DOMContentLoaded", async () => {
    
    // Находим нужные элементы
    const projectSelect = document.getElementById('select-project');
    const btnParse = document.getElementById('btn-parse');
    const btnSave = document.getElementById('btn-save');
    const btnCancel = document.getElementById('btn-cancel');
    const btnReset = document.getElementById('btn-reset');

    // Привязываем события кликов к функциям
    btnParse.addEventListener('click', processText);
    btnSave.addEventListener('click', saveData);
    btnCancel.addEventListener('click', resetForm);
    btnReset.addEventListener('click', resetForm);

    // Загружаем список проектов с сервера
    try {
        const response = await fetch(`${API_BASE_URL}/projects`);
        if (!response.ok) throw new Error("Бэкенд недоступен");
        const projects = await response.json();
        
        projectSelect.innerHTML = projects.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
    } catch (error) {
        console.warn("Бэкенд недоступен. Загружаем Mock-проекты.");
        projectSelect.innerHTML = `
            <option value="1">Редизайн сайта</option>
            <option value="2">CRM-интеграция</option>
            <option value="3">Мобильное приложение</option>
        `;
    }
});

// 3. Функция отправки текста в ИИ
async function processText() {
    const textInput = document.getElementById('user-text').value.trim();
    const errorMsg = document.getElementById('error-message');
    const btnParse = document.getElementById('btn-parse');
    const loader = document.getElementById('loader-parse');

    if (!textInput) {
        errorMsg.textContent = "Пожалуйста, напишите хотя бы пару слов.";
        errorMsg.classList.remove('hidden');
        return;
    }

    // Состояние загрузки
    errorMsg.classList.add('hidden');
    btnParse.disabled = true;
    btnParse.classList.add('opacity-75', 'cursor-not-allowed');
    loader.classList.remove('hidden');

    originalText = textInput;

    try {
        const response = await fetch(`${API_BASE_URL}/parse`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: textInput })
        });

        if (!response.ok) throw new Error("Ошибка сервера при обработке ИИ");
        
        const data = await response.json(); 

        document.getElementById('select-project').value = data.project_id || "";
        document.getElementById('input-hours').value = data.hours || "";

        document.getElementById('step-input').classList.add('hidden');
        document.getElementById('step-confirm').classList.remove('hidden');

    } catch (error) {
        console.error(error);
        errorMsg.textContent = "Не удалось связаться с ИИ. Проверьте соединение с бэкендом.";
        errorMsg.classList.remove('hidden');
    } finally {
        btnParse.disabled = false;
        btnParse.classList.remove('opacity-75', 'cursor-not-allowed');
        loader.classList.add('hidden');
    }
}

// 4. Функция сохранения результата
async function saveData() {
    const btnSave = document.getElementById('btn-save');
    const projectId = document.getElementById('select-project').value;
    const hours = document.getElementById('input-hours').value;

    btnSave.textContent = "Сохранение...";
    btnSave.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: CURRENT_USER_ID,
                project_id: parseInt(projectId),
                hours: parseFloat(hours),
                raw_text: originalText
            })
        });

        if (!response.ok) throw new Error("Ошибка при сохранении");

        document.getElementById('step-confirm').classList.add('hidden');
        document.getElementById('success-message').classList.remove('hidden');

    } catch (error) {
        alert("Ошибка сохранения: " + error.message);
        btnSave.textContent = "Всё верно, сохранить";
        btnSave.disabled = false;
    }
}

// 5. Функция сброса формы
function resetForm() {
    document.getElementById('user-text').value = '';
    document.getElementById('step-input').classList.remove('hidden');
    document.getElementById('step-confirm').classList.add('hidden');
    document.getElementById('success-message').classList.add('hidden');
    document.getElementById('btn-save').textContent = "Всё верно, сохранить";
    document.getElementById('btn-save').disabled = false;
}