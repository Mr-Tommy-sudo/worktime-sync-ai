// =====================================================================
//  WorkTime Sync — HR Dashboard
//  Связывает UI с FastAPI бэкендом (см. Backend/main.py)
// =====================================================================

const API_BASE_URL = 'http://127.0.0.1:8000';

// Глобальное состояние UI
const state = {
    currentTeamId: null,
    teams: [],
    dashboard: null,           // последний ответ /api/dashboard/team/{id}
    filter: { search: '', risk: 'all', format: 'all' },
    charts: { risk: null, format: null, load: null },
    heatmap: { date: null },
};

// Локализация форматов работы
const WORK_FORMAT_LABEL = {
    office: 'Офис',
    remote: 'Удалёнка',
    hybrid: 'Гибрид',
};
const formatWorkFormat = (key) => WORK_FORMAT_LABEL[key] || key;

// =====================================================================
//  ИНИЦИАЛИЗАЦИЯ
// =====================================================================
document.addEventListener('DOMContentLoaded', () => {
    bindUI();
    bootstrap();
});

function bindUI() {
    document.getElementById('btn-generate-data').addEventListener('click', generateTestData);
    document.getElementById('btn-refresh').addEventListener('click', () => loadDashboard(state.currentTeamId));
    document.getElementById('btn-send-chat').addEventListener('click', sendChatMessage);
    document.getElementById('chat-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendChatMessage();
    });

    document.getElementById('team-selector').addEventListener('change', (e) => {
        const id = parseInt(e.target.value, 10);
        if (!isNaN(id)) {
            state.currentTeamId = id;
            loadDashboard(id);
        }
    });

    document.getElementById('search-input').addEventListener('input', (e) => {
        state.filter.search = e.target.value.toLowerCase().trim();
        renderEmployees();
    });
    document.getElementById('risk-filter').addEventListener('change', (e) => {
        state.filter.risk = e.target.value;
        renderEmployees();
    });
    document.getElementById('format-filter').addEventListener('change', (e) => {
        state.filter.format = e.target.value;
        renderEmployees();
    });

    // Подсказки в чате
    document.querySelectorAll('.suggest-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.getElementById('chat-input').value = btn.dataset.q;
            sendChatMessage();
        });
    });

    // Heatmap
    const dateInput = document.getElementById('heatmap-date');
    state.heatmap.date = formatDate(addDays(new Date(), 1));
    dateInput.value = state.heatmap.date;
    dateInput.addEventListener('change', () => {
        state.heatmap.date = dateInput.value;
        loadHeatmap();
    });
    document.getElementById('btn-heatmap-today').addEventListener('click', () => {
        state.heatmap.date = formatDate(new Date());
        dateInput.value = state.heatmap.date;
        loadHeatmap();
    });
    document.getElementById('btn-heatmap-tomorrow').addEventListener('click', () => {
        state.heatmap.date = formatDate(addDays(new Date(), 1));
        dateInput.value = state.heatmap.date;
        loadHeatmap();
    });

    // Модалки
    document.getElementById('btn-add-employee').addEventListener('click', () => openModal('modal-employee'));
    document.getElementById('btn-add-event').addEventListener('click', () => {
        populateEmployeeSelect();
        openModal('modal-event');
    });
    document.getElementById('btn-create-team').addEventListener('click', () => openModal('modal-team'));
    document.getElementById('btn-random-employee').addEventListener('click', () => {
        populateRandomTeamSelect();
        openModal('modal-random');
    });
    document.getElementById('team-tile-add-employee').addEventListener('click', () => openModal('modal-employee'));

    document.querySelectorAll('.modal-close').forEach(b => {
        b.addEventListener('click', () => closeModal(b.dataset.target));
    });
    document.getElementById('form-employee').addEventListener('submit', submitEmployee);
    document.getElementById('form-event').addEventListener('submit', submitEvent);
    document.getElementById('form-team').addEventListener('submit', submitTeam);
    document.getElementById('form-random').addEventListener('submit', submitRandomEmployee);

    // Делегирование: клик по карточке сотрудника / кнопкам внутри
    document.getElementById('employees-container').addEventListener('click', (e) => {
        const releaseBtn = e.target.closest('[data-action="release"]');
        if (releaseBtn) {
            e.stopPropagation();
            askRelease(parseInt(releaseBtn.dataset.employeeId, 10), releaseBtn.dataset.employeeName);
            return;
        }
        const editBtn = e.target.closest('[data-action="edit-task"]');
        if (editBtn) {
            e.stopPropagation();
            const wrap = editBtn.closest('.task-inline');
            startEditTask(wrap, parseInt(wrap.dataset.employeeId, 10));
            return;
        }
        const card = e.target.closest('.employee-card');
        if (card && card.dataset.employeeId) {
            openProfile(parseInt(card.dataset.employeeId, 10));
        }
    });

    // Кликабельные ячейки heatmap: открываем quick popover
    document.getElementById('heatmap-container').addEventListener('click', (e) => {
        const cell = e.target.closest('.heatmap-cell[data-employee-id]');
        if (cell) {
            openQuickEvent(e, {
                employee_id: parseInt(cell.dataset.employeeId, 10),
                employee_name: cell.dataset.employeeName,
                date: cell.dataset.date,
                hour: cell.dataset.hour ? parseInt(cell.dataset.hour, 10) : null,
            });
            return;
        }
        const hourCell = e.target.closest('.heatmap-hour[data-hour]');
        if (hourCell) {
            // Клик по часу — без выбора сотрудника, спросим в попапе кого
            openQuickEvent(e, {
                employee_id: null,
                date: hourCell.dataset.date,
                hour: parseInt(hourCell.dataset.hour, 10),
            });
        }
    });

    // Подтверждение освобождения
    document.getElementById('btn-release-confirm').addEventListener('click', confirmRelease);

    // Quick event popover
    document.getElementById('quick-event-close').addEventListener('click', closeQuickEvent);
    document.querySelectorAll('.quick-event-btn').forEach(b => {
        b.addEventListener('click', () => createQuickEvent(b.dataset.type));
    });
    document.addEventListener('click', (e) => {
        const pop = document.getElementById('quick-event-popover');
        if (pop.classList.contains('hidden')) return;
        if (pop.contains(e.target)) return;
        if (e.target.closest('.heatmap-cell, .heatmap-hour')) return;
        closeQuickEvent();
    });
}

async function bootstrap() {
    await loadTeams();
    if (state.currentTeamId) {
        await loadDashboard(state.currentTeamId);
    }
    pingAI();
}

// =====================================================================
//  HTTP-обёртка
// =====================================================================
async function api(path, options = {}) {
    const res = await fetch(`${API_BASE_URL}${path}`, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
    });
    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const err = await res.json();
            if (err.detail) detail = err.detail;
        } catch (_) { /* ignore */ }
        throw new Error(detail);
    }
    return res.status === 204 ? null : res.json();
}

// =====================================================================
//  КОМАНДЫ
// =====================================================================
async function loadTeams() {
    const selector = document.getElementById('team-selector');
    try {
        const teams = await api('/api/teams');
        state.teams = teams;

        if (!teams.length) {
            selector.innerHTML = '<option value="">Нет команд</option>';
            showEmptyState('БД пуста. Создайте команду или нажмите «Тестовые данные» для демо.');
            document.getElementById('team-tile-name').textContent = 'Нет команд';
            document.getElementById('team-tile-meta').textContent = 'создайте команду или загрузите тестовые данные';
            return;
        }

        selector.innerHTML = teams
            .map(t => `<option value="${t.id}">${escapeHtml(t.name)} (${t.members_count})</option>`)
            .join('');

        const realTeams = teams.filter(t => t.id !== 0);
        if (state.currentTeamId === null || state.currentTeamId === undefined ||
            !teams.some(t => t.id === state.currentTeamId)) {
            state.currentTeamId = (realTeams[0] && realTeams[0].id) || teams[0].id;
        }
        selector.value = String(state.currentTeamId);
    } catch (err) {
        console.error(err);
        selector.innerHTML = '<option value="">Ошибка</option>';
        toast(`Не удалось загрузить команды: ${err.message}`, 'error');
    }
}

// =====================================================================
//  ДАШБОРД
// =====================================================================
async function loadDashboard(teamId) {
    if (!teamId && teamId !== 0) return;

    if (teamId === 0) {
        await loadReserve();
        return;
    }

    setLoadingDashboard();
    try {
        const data = await api(`/api/dashboard/team/${teamId}`);
        state.dashboard = data;
        renderDashboard();
    } catch (err) {
        console.error(err);
        showEmptyState(err.message);
    }
}

async function loadReserve() {
    setLoadingDashboard();
    try {
        const list = await api('/api/reserve');
        state.dashboard = {
            team_id: 0,
            team_name: 'В резерве',
            members_diagnostics: [],
            best_meeting_times: [],
        };
        document.getElementById('team-name').textContent = 'В резерве';
        document.getElementById('team-tile-name').textContent = 'В резерве';
        document.getElementById('team-tile-meta').textContent = `сотрудников: ${list.length}`;

        // Прячем чарты и heatmap
        ['kpi-total','kpi-avg-risk','kpi-high-risk','kpi-stale'].forEach(id =>
            document.getElementById(id).textContent = '—');

        const container = document.getElementById('employees-container');
        if (!list.length) {
            container.innerHTML = `<div class="text-center text-gray-400 py-6">
                <i class="fa-solid fa-couch mr-2"></i>В резерве пока никого нет
            </div>`;
            return;
        }
        container.innerHTML = list.map(e => `
            <div class="custom-card border border-gray-200 rounded-lg p-4 flex items-center justify-between gap-3">
                <div>
                    <h4 class="font-bold text-gray-800">${escapeHtml(e.name)}</h4>
                    <p class="text-xs text-gray-500">
                        ${escapeHtml(e.position || 'Сотрудник')} ·
                        ${escapeHtml(formatWorkFormat(e.work_format))} ·
                        ${escapeHtml(e.timezone)}
                    </p>
                </div>
                <button class="text-xs px-3 py-1.5 rounded bg-emerald-500 text-white hover:bg-emerald-600"
                    data-restore-id="${e.id}">
                    <i class="fa-solid fa-rotate-left mr-1"></i>Вернуть в команду
                </button>
            </div>
        `).join('');

        container.querySelectorAll('[data-restore-id]').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    await api(`/api/employees/${btn.dataset.restoreId}/restore`, { method: 'PATCH' });
                    toast('Сотрудник возвращён в активный статус', 'success');
                    await loadTeams();
                    await loadReserve();
                } catch (err) { toast(err.message, 'error'); }
            });
        });

        document.getElementById('meeting-windows').innerHTML = '';
        document.getElementById('heatmap-container').innerHTML =
            '<div class="text-center text-gray-400 py-4">Карта доступности недоступна для резерва</div>';
    } catch (err) {
        showEmptyState(err.message);
    }
}

function setLoadingDashboard() {
    document.getElementById('employees-container').innerHTML =
        `<div class="text-center text-gray-500 py-4"><i class="fa-solid fa-spinner fa-spin mr-2"></i> Загрузка данных...</div>`;
    document.getElementById('meeting-windows').innerHTML = `<li class="text-sm text-gray-500">Загрузка...</li>`;
}

function showEmptyState(message) {
    document.getElementById('team-name').textContent = '—';
    ['kpi-total', 'kpi-avg-risk', 'kpi-high-risk', 'kpi-stale'].forEach(id => {
        document.getElementById(id).textContent = '—';
    });
    document.getElementById('employees-container').innerHTML =
        `<div class="text-red-600 p-4 bg-red-50 rounded border border-red-100">
            <i class="fa-solid fa-triangle-exclamation mr-2"></i>${escapeHtml(message)}
        </div>`;
    document.getElementById('meeting-windows').innerHTML =
        `<li class="text-sm text-gray-400">Нет данных</li>`;
    destroyCharts();
}

function renderDashboard() {
    const data = state.dashboard;
    document.getElementById('team-name').textContent = data.team_name;
    document.getElementById('team-tile-name').textContent = data.team_name;
    document.getElementById('team-tile-meta').textContent =
        `сотрудников: ${data.members_diagnostics.length}`;

    renderKpi(data);
    renderCharts(data);
    renderEmployees();
    renderMeetingWindows(data);
    loadHeatmap();
}

function renderKpi(data) {
    const members = data.members_diagnostics;
    const total = members.length;

    const avgRisk = total
        ? (members.reduce((s, m) => s + m.metrics.integrated_risk, 0) / total)
        : 0;
    const highRisk = members.filter(m =>
        m.metrics.risk_level === 'Высокий риск' || m.metrics.risk_level === 'Критический риск'
    ).length;
    const stale = members.filter(m => m.metrics.days_since_last_update > 30).length;

    document.getElementById('kpi-total').textContent = total;
    document.getElementById('kpi-total-sub').textContent = `в команде «${data.team_name}»`;
    document.getElementById('kpi-avg-risk').textContent = avgRisk.toFixed(2);
    document.getElementById('kpi-high-risk').textContent = highRisk;
    document.getElementById('kpi-stale').textContent = stale;
}

// =====================================================================
//  ГРАФИКИ (Chart.js)
// =====================================================================
function destroyCharts() {
    Object.values(state.charts).forEach(c => c && c.destroy());
    state.charts = { risk: null, format: null, load: null };
}

function renderCharts(data) {
    destroyCharts();
    const members = data.members_diagnostics;

    // 1. Распределение по риску (doughnut)
    const riskBuckets = { 'Низкий риск': 0, 'Средний риск': 0, 'Высокий риск': 0, 'Критический риск': 0 };
    members.forEach(m => { riskBuckets[m.metrics.risk_level] = (riskBuckets[m.metrics.risk_level] || 0) + 1; });

    const riskTooltip = document.getElementById('risk-tooltip');
    state.charts.risk = new Chart(document.getElementById('chart-risk'), {
        type: 'doughnut',
        data: {
            labels: Object.keys(riskBuckets),
            datasets: [{
                data: Object.values(riskBuckets),
                backgroundColor: ['#86efac', '#fde68a', '#fdba74', '#fca5a5'],
                borderWidth: 0,
                hoverOffset: 14,
            }],
        },
        options: {
            plugins: {
                legend: { position: 'bottom', labels: { font: { size: 11 } } },
                tooltip: { enabled: true },
            },
            cutout: '60%',
            onHover: (evt, items) => {
                if (!riskTooltip) return;
                if (items.length) {
                    const i = items[0].index;
                    const label = Object.keys(riskBuckets)[i];
                    const val = Object.values(riskBuckets)[i];
                    riskTooltip.textContent = `${label}: ${val} чел.`;
                } else {
                    riskTooltip.textContent = 'Наведите на сегмент';
                }
            },
        },
    });

    // 2. Формат работы (pie)
    const formatBuckets = {};
    members.forEach(m => {
        const f = formatWorkFormat(m.employee.work_format);
        formatBuckets[f] = (formatBuckets[f] || 0) + 1;
    });

    const formatTooltip = document.getElementById('format-tooltip');
    state.charts.format = new Chart(document.getElementById('chart-format'), {
        type: 'pie',
        data: {
            labels: Object.keys(formatBuckets),
            datasets: [{
                data: Object.values(formatBuckets),
                backgroundColor: ['#a5b4fc', '#c4b5fd', '#fbcfe8'],
                borderWidth: 0,
                hoverOffset: 14,
            }],
        },
        options: {
            plugins: { legend: { position: 'bottom', labels: { font: { size: 11 } } } },
            onHover: (evt, items) => {
                if (!formatTooltip) return;
                if (items.length) {
                    const i = items[0].index;
                    const label = Object.keys(formatBuckets)[i];
                    const val = Object.values(formatBuckets)[i];
                    formatTooltip.textContent = `${label}: ${val} чел.`;
                } else {
                    formatTooltip.textContent = 'Наведите на сегмент';
                }
            },
        },
    });

    // 3. Загрузка по сотрудникам (bar)
    state.charts.load = new Chart(document.getElementById('chart-load'), {
        type: 'bar',
        data: {
            labels: members.map(m => shortName(m.employee.name)),
            datasets: [{
                label: 'Загрузка, %',
                data: members.map(m => Math.round(m.metrics.load_level * 100)),
                backgroundColor: members.map(m =>
                    m.metrics.load_level > 0.8 ? '#ef4444' :
                    m.metrics.load_level > 0.5 ? '#f59e0b' : '#6366f1'
                ),
                borderRadius: 4,
            }],
        },
        options: {
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, max: 100, ticks: { font: { size: 10 } } },
                x: { ticks: { font: { size: 10 } } },
            },
        },
    });
}

// =====================================================================
//  СПИСОК СОТРУДНИКОВ + ФИЛЬТРЫ
// =====================================================================
function renderEmployees() {
    if (!state.dashboard) return;

    const container = document.getElementById('employees-container');
    const { search, risk, format } = state.filter;

    const filtered = state.dashboard.members_diagnostics.filter(m => {
        const matchSearch = !search || m.employee.name.toLowerCase().includes(search);
        const matchRisk = risk === 'all' || m.metrics.risk_level === risk;
        const matchFormat = format === 'all' || m.employee.work_format === format;
        return matchSearch && matchRisk && matchFormat;
    });

    if (!filtered.length) {
        container.innerHTML =
            `<div class="text-center text-gray-400 py-6">
                <i class="fa-solid fa-filter-circle-xmark mr-2"></i>Нет сотрудников по выбранным фильтрам
            </div>`;
        return;
    }

    container.innerHTML = filtered.map(renderEmployeeCard).join('');
}

function renderEmployeeCard(member) {
    const emp = member.employee;
    const m = member.metrics;
    const recs = member.recommendations;

    const riskColor = riskBadgeClass(m.risk_level);
    const updateColor = m.days_since_last_update > 30 ? 'text-red-500' : 'text-gray-700';
    const conflictColor = m.conflict_ratio > 0.2 ? 'text-orange-500' : 'text-gray-700';
    const loadColor = m.load_level > 0.8 ? 'text-red-500' : 'text-gray-700';

    const taskText = emp.current_task || 'Задача не задана';

    return `
        <div class="custom-card employee-card border border-gray-200 rounded-lg p-4 hover:shadow-md transition cursor-pointer"
             data-employee-id="${emp.id}" title="Открыть профиль">
            <div class="flex justify-between items-start mb-3 gap-3">
                <div class="min-w-0">
                    <h4 class="font-bold text-gray-800 text-lg flex items-center gap-2 flex-wrap">
                        ${escapeHtml(emp.name)}
                        <i class="fa-solid fa-arrow-up-right-from-square text-xs text-indigo-400"></i>
                    </h4>
                    <p class="text-xs text-gray-500">
                        ${emp.position ? `<span class="text-gray-700">${escapeHtml(emp.position)}</span> · ` : ''}
                        Формат: ${escapeHtml(formatWorkFormat(emp.work_format))} ·
                        Часовой пояс: ${escapeHtml(emp.timezone)}
                    </p>
                </div>
                <div class="flex flex-col items-end gap-2">
                    <span class="text-xs font-semibold px-2 py-1 rounded border ${riskColor} whitespace-nowrap">
                        ${escapeHtml(m.risk_level)} (R: ${m.integrated_risk.toFixed(2)})
                    </span>
                    <button class="btn-release" data-employee-id="${emp.id}" data-employee-name="${escapeHtml(emp.name)}"
                        data-action="release" title="Перевести в резерв">
                        <i class="fa-solid fa-user-slash mr-1"></i>Освободить
                    </button>
                </div>
            </div>

            <!-- Текущая задача -->
            <div class="task-inline mb-3" data-employee-id="${emp.id}">
                <i class="fa-solid fa-bolt text-indigo-500"></i>
                <span class="task-label text-[10px] uppercase text-indigo-400 font-semibold">Текущая задача:</span>
                <span class="task-text" title="${escapeHtml(taskText)}">${escapeHtml(taskText)}</span>
                <button class="task-edit-btn" data-action="edit-task" title="Редактировать задачу">
                    <i class="fa-solid fa-pen"></i>
                </button>
            </div>

            <div class="grid grid-cols-4 gap-2 mb-4 text-center">
                ${metricCell('Актуальность (A)', m.relevance_score.toFixed(2))}
                ${metricCell('Дней без обн.', m.days_since_last_update, updateColor)}
                ${metricCell('Конфликты (C)', `${(m.conflict_ratio * 100).toFixed(0)}%`, conflictColor)}
                ${metricCell('Загрузка (L)', `${(m.load_level * 100).toFixed(0)}%`, loadColor)}
            </div>

            <div class="bg-indigo-50/50 rounded p-3 text-sm border-l-2 border-indigo-400">
                <div class="font-semibold text-indigo-800 mb-1 text-xs">Рекомендации ИИ:</div>
                <ul class="list-disc pl-4 text-indigo-700 space-y-1 text-xs">
                    ${recs.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
                </ul>
            </div>
        </div>
    `;
}

function metricCell(label, value, valueClass = 'text-gray-700') {
    return `
        <div class="bg-gray-50 p-2 rounded border border-gray-100">
            <div class="text-[10px] text-gray-400 uppercase">${label}</div>
            <div class="font-semibold ${valueClass}">${value}</div>
        </div>
    `;
}

function riskBadgeClass(level) {
    switch (level) {
        case 'Средний риск':    return 'bg-yellow-100 text-yellow-700 border-yellow-200';
        case 'Высокий риск':    return 'bg-orange-100 text-orange-700 border-orange-200';
        case 'Критический риск':return 'bg-red-100 text-red-700 border-red-200';
        default:                return 'bg-green-100 text-green-700 border-green-200';
    }
}

// =====================================================================
//  ОКНА ВСТРЕЧ
// =====================================================================
function renderMeetingWindows(data) {
    const list = document.getElementById('meeting-windows');
    const windows = data.best_meeting_times || [];

    if (!windows.length || windows[0].includes('нет общих окон') || windows[0].includes('не найдены')) {
        list.innerHTML = `<li class="text-sm text-red-500 p-2 bg-red-50 rounded">${escapeHtml(windows[0] || 'Окна не найдены')}</li>`;
        return;
    }

    list.innerHTML = windows.map(w =>
        `<li class="text-sm text-gray-700 p-2 bg-green-50 rounded border border-green-100">
            <i class="fa-regular fa-clock text-green-500 mr-2"></i>${escapeHtml(w)}
        </li>`
    ).join('');
}

// =====================================================================
//  ГЕНЕРАЦИЯ MVP-ДАННЫХ
// =====================================================================
async function generateTestData() {
    const btn = document.getElementById('btn-generate-data');
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Генерация...`;

    try {
        await api('/generate_test_data/', { method: 'POST' });
        toast('Тестовые данные загружены', 'success');
        await loadTeams();
        if (state.currentTeamId) await loadDashboard(state.currentTeamId);
    } catch (err) {
        toast(err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-database mr-1"></i> Тестовые данные`;
    }
}

// =====================================================================
//  ЧАТ С AI (GigaChat / fallback)
// =====================================================================
const chatHistory = [];  // { role: 'user'|'assistant', content }

async function sendChatMessage() {
    const inputField = document.getElementById('chat-input');
    const message = inputField.value.trim();
    if (!message) return;

    const chat = document.getElementById('chat-messages');

    chat.insertAdjacentHTML('beforeend', `
        <div class="bg-indigo-600 text-white p-2 rounded shadow-sm text-sm ml-8 self-end">
            ${escapeHtml(message)}
        </div>
    `);
    inputField.value = '';
    chat.scrollTop = chat.scrollHeight;

    chatHistory.push({ role: 'user', content: message });

    const loaderId = `loader-${Date.now()}`;
    chat.insertAdjacentHTML('beforeend', `
        <div id="${loaderId}" class="p-2 text-sm text-gray-400">
            <i class="fa-solid fa-spinner fa-spin"></i> ИИ думает...
        </div>
    `);
    chat.scrollTop = chat.scrollHeight;

    try {
        const data = await api('/api/ai/chat', {
            method: 'POST',
            body: JSON.stringify({
                team_id: state.currentTeamId || null,
                messages: chatHistory.slice(-12),  // ограничим длину истории
            }),
        });
        document.getElementById(loaderId)?.remove();
        chatHistory.push({ role: 'assistant', content: data.answer });
        const providerLabel = data.provider === 'gigachat'
            ? `<span class="text-emerald-500 text-[10px] block mb-1 font-semibold">GigaChat</span>`
            : `<span class="text-indigo-400 text-[10px] block mb-1 font-semibold">AI Ассистент</span>`;
        chat.insertAdjacentHTML('beforeend', `
            <div class="bg-white p-2 rounded shadow-sm text-sm border-l-2 ${data.provider === 'gigachat' ? 'border-emerald-400' : 'border-indigo-400'} mr-8 whitespace-pre-line">
                ${providerLabel}
                ${escapeHtml(data.answer)}
            </div>
        `);
        chat.scrollTop = chat.scrollHeight;
        // Обновим бейдж после ответа
        updateAIBadge(!!data.online, data.provider || 'local');
    } catch (err) {
        document.getElementById(loaderId)?.remove();
        chat.insertAdjacentHTML('beforeend', `
            <div class="bg-red-50 p-2 rounded shadow-sm text-sm border-l-2 border-red-400 text-red-700">
                Ошибка связи с сервером: ${escapeHtml(err.message)}
            </div>
        `);
    }
}

async function pingAI() {
    try {
        const h = await api('/api/ai/health');
        if (h.online) {
            updateAIBadge(true, 'gigachat');
        } else {
            updateAIBadge(false, 'local');
        }
    } catch (_) {
        updateAIBadge(false, 'local');
    }
}

function updateAIBadge(online, provider) {
    const badge = document.getElementById('ai-provider-badge');
    const text = document.getElementById('ai-status-text');
    if (!badge || !text) return;
    badge.classList.remove('online', 'offline');
    if (online) {
        badge.classList.add('online');
        text.textContent = `GigaChat · онлайн`;
    } else {
        badge.classList.add('offline');
        text.textContent = provider === 'gigachat' ? 'GigaChat · оффлайн' : 'локальный режим';
    }
}

// =====================================================================
//  МОДАЛКИ
// =====================================================================
function openModal(id) {
    document.getElementById(id).classList.remove('hidden');
}
function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
}

function populateEmployeeSelect() {
    const select = document.getElementById('event-employee-select');
    if (!state.dashboard) {
        select.innerHTML = '<option value="">Сначала выберите команду</option>';
        return;
    }
    select.innerHTML = state.dashboard.members_diagnostics
        .map(m => `<option value="${m.employee.id}">${escapeHtml(m.employee.name)}</option>`)
        .join('');
}

function populateRandomTeamSelect() {
    const select = document.getElementById('random-team-select');
    if (!state.teams.length) {
        select.innerHTML = '<option value="">Сначала создайте команду</option>';
        return;
    }
    select.innerHTML = state.teams
        .map(t => `<option value="${t.id}" ${t.id === state.currentTeamId ? 'selected' : ''}>${escapeHtml(t.name)}</option>`)
        .join('');
}

async function submitTeam(e) {
    e.preventDefault();
    const fd = new FormData(e.target);
    const name = (fd.get('name') || '').trim();
    if (!name) return toast('Введите название команды', 'error');

    try {
        await api('/api/teams', { method: 'POST', body: JSON.stringify({ name }) });
        toast(`Команда «${name}» создана`, 'success');
        closeModal('modal-team');
        e.target.reset();
        await loadTeams();   // не переключаемся, сохраняем текущую
        if (state.currentTeamId) await loadDashboard(state.currentTeamId);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function submitRandomEmployee(e) {
    e.preventDefault();
    const fd = new FormData(e.target);
    const teamId = parseInt(fd.get('team_id'), 10);
    if (!teamId) return toast('Выберите команду', 'error');

    try {
        const created = await api('/api/employees/random', {
            method: 'POST',
            body: JSON.stringify({ team_id: teamId }),
        });
        toast(`Создан сотрудник: ${created.name}`, 'success');
        closeModal('modal-random');
        await loadTeams();
        if (state.currentTeamId === teamId) {
            await loadDashboard(teamId);
        }
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function submitEmployee(e) {
    e.preventDefault();
    if (!state.currentTeamId) return toast('Сначала выберите команду', 'error');

    const fd = new FormData(e.target);
    const payload = {
        name: fd.get('name'),
        email: fd.get('email'),
        team_id: state.currentTeamId,
        work_days: fd.get('work_days'),
        work_start: fd.get('work_start'),
        work_end: fd.get('work_end'),
        timezone: fd.get('timezone'),
        work_format: fd.get('work_format'),
        exceptions: [],
    };

    try {
        await api('/employees/', { method: 'POST', body: JSON.stringify(payload) });
        toast('Сотрудник добавлен', 'success');
        closeModal('modal-employee');
        e.target.reset();
        await loadTeams();
        await loadDashboard(state.currentTeamId);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function submitEvent(e) {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = {
        employee_id: parseInt(fd.get('employee_id'), 10),
        title: fd.get('title'),
        start_time: new Date(fd.get('start_time')).toISOString(),
        end_time: new Date(fd.get('end_time')).toISOString(),
        event_type: fd.get('event_type'),
        source: fd.get('source'),
    };

    try {
        await api('/events/', { method: 'POST', body: JSON.stringify(payload) });
        toast('Событие добавлено', 'success');
        closeModal('modal-event');
        e.target.reset();
        await loadDashboard(state.currentTeamId);
    } catch (err) {
        toast(err.message, 'error');
    }
}

// =====================================================================
//  УТИЛИТЫ
// =====================================================================
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function shortName(name) {
    const parts = String(name).split(' ');
    if (parts.length < 2) return name;
    return `${parts[0]} ${parts[1][0]}.`;
}

function toast(message, kind = 'info') {
    const styles = {
        info:    'bg-gray-800 text-white',
        success: 'bg-emerald-600 text-white',
        error:   'bg-red-600 text-white',
    };
    const div = document.createElement('div');
    div.className = `${styles[kind] || styles.info} px-4 py-2 rounded shadow text-sm animate-fade-in`;
    div.textContent = message;
    document.getElementById('toast-container').appendChild(div);
    setTimeout(() => div.remove(), 3500);
}

// =====================================================================
//  HEATMAP ДОСТУПНОСТИ
// =====================================================================
async function loadHeatmap() {
    const container = document.getElementById('heatmap-container');
    if (!state.currentTeamId) return;

    container.innerHTML = `<div class="text-center text-gray-500 py-4">
        <i class="fa-solid fa-spinner fa-spin mr-2"></i>Загрузка карты...
    </div>`;

    try {
        const params = new URLSearchParams({ hour_start: 9, hour_end: 20 });
        if (state.heatmap.date) params.set('date', state.heatmap.date);
        const data = await api(`/api/team/${state.currentTeamId}/availability_map?${params.toString()}`);
        renderHeatmap(data);
    } catch (err) {
        container.innerHTML = `<div class="text-red-600 p-3 bg-red-50 rounded border border-red-100">
            <i class="fa-solid fa-triangle-exclamation mr-2"></i>${escapeHtml(err.message)}
        </div>`;
    }
}

function renderHeatmap(data) {
    const container = document.getElementById('heatmap-container');
    if (!data.employees.length) {
        container.innerHTML = `<div class="text-center text-gray-400 py-4">В команде нет сотрудников</div>`;
        return;
    }

    const slotCount = data.slots.length;
    const gridTemplate = `200px repeat(${slotCount}, minmax(48px, 1fr))`;

    // Шапка с часами
    const header = `
        <div class="heatmap-row" style="grid-template-columns:${gridTemplate}">
            <div></div>
            ${data.slots.map(s => `<div class="heatmap-hour" data-date="${data.date}" data-hour="${s.hour}" title="Добавить событие на ${s.label}">${s.label}</div>`).join('')}
        </div>
    `;

    // Строки сотрудников
    const empRows = data.employees.map(emp => {
        const cells = data.slots.map(slot => {
            const st = slot.statuses.find(x => x.employee_id === emp.id);
            return cellHtml(st, emp, slot, data.date);
        }).join('');
        return `
            <div class="heatmap-row" style="grid-template-columns:${gridTemplate}">
                <div class="heatmap-name" title="${escapeHtml(emp.name)} · ${escapeHtml(emp.timezone)}">
                    ${escapeHtml(emp.name)}<span class="tz">${escapeHtml(emp.timezone)}</span>
                </div>
                ${cells}
            </div>
        `;
    }).join('');

    // Командная строка
    const teamCells = data.slots.map(slot => {
        const cls = slot.team_available ? 'heatmap-team team-on' : 'heatmap-team';
        const txt = slot.team_available ? '<i class="fa-solid fa-check"></i>' : '';
        return `<div class="${cls}" title="${slot.team_available ? 'Все свободны' : 'Кто-то занят'}">${txt}</div>`;
    }).join('');

    const teamRow = `
        <div class="heatmap-row mt-2" style="grid-template-columns:${gridTemplate}">
            <div class="heatmap-name font-semibold text-gray-700">
                <i class="fa-solid fa-users text-emerald-500 mr-1"></i>Командное окно
            </div>
            ${teamCells}
        </div>
    `;

    const summary = data.common_window_hours.length
        ? `<div class="text-xs text-emerald-700 mb-3"><i class="fa-solid fa-circle-check mr-1"></i>
             Общие окна команды: <b>${data.common_window_hours.join(', ')}</b></div>`
        : `<div class="text-xs text-orange-600 mb-3"><i class="fa-solid fa-circle-exclamation mr-1"></i>
             На эту дату нет общих окон в диапазоне ${data.hour_start}:00–${data.hour_end}:00</div>`;

    container.innerHTML = `
        ${summary}
        <div class="heatmap">
            ${header}
            ${empRows}
            ${teamRow}
        </div>
    `;
}

function cellHtml(st, emp, slot, date) {
    const dataAttrs = (emp && slot && date)
        ? ` data-employee-id="${emp.id}" data-employee-name="${escapeHtml(emp.name)}" data-date="${date}" data-hour="${slot.hour}"`
        : '';
    if (!st) return `<div class="heatmap-cell cell-off"${dataAttrs}></div>`;
    if (st.status === 'free')     return `<div class="heatmap-cell cell-free"${dataAttrs} title="Свободен · клик — добавить событие"></div>`;
    if (st.status === 'busy')     return `<div class="heatmap-cell cell-busy"${dataAttrs} title="${escapeHtml(st.title || 'Занят')}"></div>`;
    if (st.status === 'vacation') return `<div class="heatmap-cell cell-vacation"${dataAttrs} title="${escapeHtml(st.title || 'Отпуск')}"><i class="fa-solid fa-umbrella-beach"></i></div>`;
    if (st.status === 'sick')     return `<div class="heatmap-cell cell-sick"${dataAttrs} title="${escapeHtml(st.title || 'Больничный')}"><i class="fa-solid fa-briefcase-medical"></i></div>`;
    return `<div class="heatmap-cell cell-off"${dataAttrs} title="Вне рабочего графика"></div>`;
}

// =====================================================================
//  ДАТЫ
// =====================================================================
function formatDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}
function addDays(d, n) {
    const out = new Date(d);
    out.setDate(out.getDate() + n);
    return out;
}

// =====================================================================
//  ПРОФИЛЬ СОТРУДНИКА (МОДАЛКА)
// =====================================================================
async function openProfile(employeeId) {
    openModal('modal-profile');
    document.getElementById('profile-header-body').innerHTML =
        `<i class="fa-solid fa-spinner fa-spin"></i> Загрузка профиля...`;
    document.getElementById('profile-body').innerHTML = '';

    try {
        const data = await api(`/api/employee/${employeeId}/profile`);
        renderProfile(data);
    } catch (err) {
        document.getElementById('profile-header-body').innerHTML =
            `<div class="text-red-600 p-3 bg-red-50 rounded">${escapeHtml(err.message)}</div>`;
    }
}

function renderProfile(data) {
    const emp = data.employee;
    const m = data.metrics;
    const initials = emp.name
        .split(' ')
        .filter(Boolean)
        .map(s => s[0])
        .slice(0, 2)
        .join('')
        .toUpperCase();

    const alertHtml = data.burnout_alert
        ? `<div class="mt-3 inline-flex items-center gap-2 bg-red-100 text-red-700 px-3 py-1.5 rounded-full text-xs font-semibold animate-pulse">
             <i class="fa-solid fa-fire"></i> ${escapeHtml(data.burnout_alert)}
           </div>`
        : `<div class="mt-3 inline-flex items-center gap-2 bg-emerald-100 text-emerald-700 px-3 py-1.5 rounded-full text-xs font-semibold">
             <i class="fa-solid fa-circle-check"></i> График в норме
           </div>`;

    document.getElementById('profile-header-body').innerHTML = `
        <div class="flex items-center gap-4">
            <div class="profile-avatar">${escapeHtml(initials)}</div>
            <div class="text-left">
                <h3 class="text-2xl font-bold text-gray-800">${escapeHtml(emp.name)}</h3>
                <p class="text-sm text-gray-500">
                    ${escapeHtml(emp.position || 'Сотрудник')} ·
                    ${escapeHtml(formatWorkFormat(emp.work_format))} ·
                    ${escapeHtml(emp.timezone)}
                </p>
                <p class="text-xs text-gray-400 mt-1">${escapeHtml(emp.email)}</p>
                ${alertHtml}
            </div>
        </div>
    `;

    document.getElementById('profile-body').innerHTML = `
        ${renderProfileMetrics(m)}
        ${renderProfileTaskBlock(emp)}
        ${renderActivityBlock(data.activity)}
        ${renderTaskHistoryBlock(data.task_history || [])}
        ${renderHistoryBlock(data.history)}
        ${renderRecommendationsBlock(data.recommendations)}
    `;

    // Привяжем редактирование текущей задачи в профиле
    const profileTaskWrap = document.getElementById('profile-task');
    if (profileTaskWrap) {
        profileTaskWrap.addEventListener('click', (e) => {
            const editBtn = e.target.closest('[data-action="edit-task"]');
            if (editBtn) {
                e.stopPropagation();
                startEditTaskInProfile(profileTaskWrap, emp.id);
            }
        });
    }
}

function renderProfileTaskBlock(emp) {
    const text = emp.current_task || 'Задача не задана';
    return `
        <div id="profile-task" class="task-inline" data-employee-id="${emp.id}">
            <i class="fa-solid fa-bolt text-indigo-500"></i>
            <span class="task-label text-[10px] uppercase text-indigo-400 font-semibold">Текущая задача:</span>
            <span class="task-text" title="${escapeHtml(text)}">${escapeHtml(text)}</span>
            <button class="task-edit-btn" data-action="edit-task" title="Редактировать задачу">
                <i class="fa-solid fa-pen"></i>
            </button>
        </div>
    `;
}

function renderTaskHistoryBlock(history) {
    if (!history || !history.length) return '';
    const items = history.map(h => `
        <li class="flex items-start gap-2 py-1.5 border-b border-gray-100 last:border-b-0">
            <i class="fa-solid ${h.is_current ? 'fa-bolt text-emerald-500' : 'fa-check text-gray-300'} mt-0.5"></i>
            <div class="flex-1">
                <div class="text-sm text-gray-800">${escapeHtml(h.text)}</div>
                <div class="text-[11px] text-gray-400">
                    ${formatDateLabel(h.started_at)}${h.ended_at ? ' — ' + formatDateLabel(h.ended_at) : ' · в работе'}
                </div>
            </div>
        </li>
    `).join('');
    return `
        <div class="border border-gray-100 rounded-xl p-4">
            <h4 class="font-semibold text-gray-800 mb-2 text-sm">
                <i class="fa-solid fa-list-check text-indigo-500 mr-1"></i>История задач
            </h4>
            <ul>${items}</ul>
        </div>
    `;
}

async function startEditTaskInProfile(wrap, employeeId) {
    // Используем тот же сценарий, но после сохранения перезагружаем профиль
    const textEl = wrap.querySelector('.task-text');
    const editBtn = wrap.querySelector('.task-edit-btn');
    const labelEl = wrap.querySelector('.task-label');
    const oldText = textEl ? textEl.textContent : '';

    if (textEl) textEl.style.display = 'none';
    if (editBtn) editBtn.style.display = 'none';
    if (labelEl) labelEl.style.display = 'none';

    const inputId = `profile-task-input-${employeeId}`;
    wrap.insertAdjacentHTML('beforeend', `
        <input id="${inputId}" type="text" value="${escapeHtml(oldText)}" class="task-input">
        <div class="task-actions">
            <button class="task-save"><i class="fa-solid fa-check"></i> Сохранить</button>
            <button class="task-cancel"><i class="fa-solid fa-xmark"></i> Отмена</button>
        </div>
    `);
    const input = document.getElementById(inputId);
    input.focus();
    input.select();

    const cancel = () => openProfile(employeeId);
    const save = async () => {
        const text = input.value.trim();
        if (!text) { toast('Текст задачи не может быть пустым', 'error'); return; }
        try {
            await api(`/api/employees/${employeeId}/task`, {
                method: 'PATCH', body: JSON.stringify({ text }),
            });
            toast('Задача обновлена', 'success');
            await openProfile(employeeId);
            await loadDashboard(state.currentTeamId);
        } catch (err) { toast(err.message, 'error'); }
    };

    wrap.querySelector('.task-save').addEventListener('click', save);
    wrap.querySelector('.task-cancel').addEventListener('click', cancel);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') save();
        if (e.key === 'Escape') cancel();
    });
}

function renderProfileMetrics(m) {
    return `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
            ${profileStat('Риск', m.integrated_risk.toFixed(2), m.risk_level, riskTextClass(m.risk_level))}
            ${profileStat('Актуальность', m.relevance_score.toFixed(2), `${m.days_since_last_update} дн без обн.`, '')}
            ${profileStat('Конфликты', `${(m.conflict_ratio * 100).toFixed(0)}%`, 'встреч вне графика', '')}
            ${profileStat('Загрузка', `${(m.load_level * 100).toFixed(0)}%`, m.load_level > 0.8 ? 'перегрузка' : 'норма',
                m.load_level > 0.8 ? 'text-red-600' : 'text-gray-700')}
        </div>
    `;
}

function profileStat(label, value, sub, valueClass) {
    return `
        <div class="bg-gray-50 rounded-lg p-3 border border-gray-100">
            <div class="text-[10px] text-gray-500 uppercase">${label}</div>
            <div class="text-xl font-bold ${valueClass || 'text-gray-800'}">${value}</div>
            <div class="text-[11px] text-gray-400 mt-0.5">${escapeHtml(sub)}</div>
        </div>
    `;
}

function riskTextClass(level) {
    switch (level) {
        case 'Средний риск':     return 'text-yellow-600';
        case 'Высокий риск':     return 'text-orange-600';
        case 'Критический риск': return 'text-red-600';
        default:                 return 'text-emerald-600';
    }
}

// ----- Stacked Bar активности -----
function renderActivityBlock(activity) {
    if (!activity || !activity.apps || !activity.apps.length) {
        return `
            <div class="border border-gray-100 rounded-xl p-4">
                <div class="flex items-center justify-between mb-2">
                    <h4 class="font-semibold text-gray-800">Реальная активность <span class="text-xs text-gray-400 font-normal">по данным Агента</span></h4>
                </div>
                <div class="text-sm text-gray-400 py-3 text-center">
                    <i class="fa-solid fa-plug-circle-xmark mr-1"></i> Логи агента отсутствуют
                </div>
            </div>
        `;
    }

    const segments = activity.apps.map(a => `
        <div class="activity-seg" style="width:${a.percentage}%;background:${a.color}" title="${escapeHtml(a.name)} — ${escapeHtml(a.time)} (${a.percentage}%)"></div>
    `).join('');

    const legend = activity.apps.map(a => `
        <div class="flex items-center gap-2 text-xs text-gray-700">
            <span class="legend-dot" style="background:${a.color}"></span>
            <span class="font-medium">${escapeHtml(a.name)}</span>
            <span class="text-gray-400">${a.percentage}% · ${escapeHtml(a.time)}</span>
        </div>
    `).join('');

    return `
        <div class="border border-gray-100 rounded-xl p-4">
            <div class="flex items-center justify-between mb-2">
                <h4 class="font-semibold text-gray-800">
                    Реальная активность
                    <span class="text-xs text-gray-400 font-normal">по данным Агента · ${escapeHtml(activity.date)}</span>
                </h4>
                <span class="text-xs text-gray-500">Отработано по трекеру: <b class="text-indigo-600">${escapeHtml(activity.total_tracked_label)}</b></span>
            </div>
            <div class="activity-bar mb-3">${segments}</div>
            <div class="grid grid-cols-2 md:grid-cols-3 gap-y-2 gap-x-4">${legend}</div>
        </div>
    `;
}

// ----- Timeline истории -----
function renderHistoryBlock(history) {
    if (!history || !history.length) {
        return `
            <div class="border border-gray-100 rounded-xl p-4">
                <h4 class="font-semibold text-gray-800 mb-2">История графика</h4>
                <div class="text-sm text-gray-400 py-2"><i class="fa-regular fa-clock mr-1"></i>История пуста</div>
            </div>
        `;
    }
    const items = history.map(h => `
        <li class="timeline-item">
            <span class="timeline-dot"><i class="fa-solid ${escapeHtml(h.icon)}"></i></span>
            <div>
                <div class="text-sm font-semibold text-gray-800">${escapeHtml(h.title)}</div>
                ${h.description ? `<div class="text-xs text-gray-500">${escapeHtml(h.description)}</div>` : ''}
                <div class="text-[11px] text-gray-400 mt-0.5">
                    ${escapeHtml(formatDateHuman(h.happened_at))} · ${h.days_ago} дн назад
                </div>
            </div>
        </li>
    `).join('');
    return `
        <div class="border border-gray-100 rounded-xl p-4">
            <h4 class="font-semibold text-gray-800 mb-3">История графика</h4>
            <ol class="timeline">${items}</ol>
        </div>
    `;
}

// ----- Рекомендации ИИ -----
function renderRecommendationsBlock(recs) {
    if (!recs || !recs.length) return '';
    return `
        <div class="border-l-4 border-indigo-400 bg-indigo-50/40 rounded-xl p-4">
            <h4 class="font-semibold text-indigo-800 mb-2 text-sm">
                <i class="fa-solid fa-robot mr-1"></i> Рекомендации ИИ
            </h4>
            <ul class="list-disc pl-5 text-sm text-indigo-700 space-y-1">
                ${recs.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
            </ul>
        </div>
    `;
}

function formatDateHuman(iso) {
    try {
        const d = new Date(iso);
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch (_) { return iso; }
}

// =====================================================================
//  БЫСТРЫЕ ДЕЙСТВИЯ: ОСВОБОДИТЬ / РЕДАКТИРОВАТЬ ЗАДАЧУ / БЫСТРЫЕ СОБЫТИЯ
// =====================================================================
let pendingRelease = null;

function askRelease(employeeId, employeeName) {
    pendingRelease = employeeId;
    document.getElementById('release-target-name').textContent = employeeName;
    openModal('modal-release');
}

async function confirmRelease() {
    if (!pendingRelease) return;
    try {
        const res = await api(`/api/employees/${pendingRelease}/release`, { method: 'PATCH' });
        toast(res.message || 'Сотрудник переведён в резерв', 'success');
        closeModal('modal-release');
        pendingRelease = null;
        await loadTeams();
        await loadDashboard(state.currentTeamId);
    } catch (err) {
        toast(err.message, 'error');
    }
}

// ----- Редактирование текущей задачи -----
function startEditTask(wrap, employeeId) {
    const textEl = wrap.querySelector('.task-text');
    const editBtn = wrap.querySelector('.task-edit-btn');
    const labelEl = wrap.querySelector('.task-label');
    const oldText = textEl ? textEl.textContent : '';

    if (textEl) textEl.style.display = 'none';
    if (editBtn) editBtn.style.display = 'none';
    if (labelEl) labelEl.style.display = 'none';

    const inputId = `task-input-${employeeId}`;
    wrap.insertAdjacentHTML('beforeend', `
        <input id="${inputId}" type="text" value="${escapeHtml(oldText)}" class="task-input">
        <div class="task-actions">
            <button class="task-save"><i class="fa-solid fa-check"></i> Сохранить</button>
            <button class="task-cancel"><i class="fa-solid fa-xmark"></i> Отмена</button>
        </div>
    `);
    const input = document.getElementById(inputId);
    input.focus();
    input.select();

    const cancel = () => renderEmployees();  // отрисуем список заново — вернёт исходный вид
    const save = async () => {
        const text = input.value.trim();
        if (!text) { toast('Текст задачи не может быть пустым', 'error'); return; }
        try {
            await api(`/api/employees/${employeeId}/task`, {
                method: 'PATCH',
                body: JSON.stringify({ text }),
            });
            toast('Задача обновлена', 'success');
            // Локально обновим в state
            if (state.dashboard) {
                const m = state.dashboard.members_diagnostics.find(x => x.employee.id === employeeId);
                if (m) m.employee.current_task = text;
            }
            renderEmployees();
        } catch (err) {
            toast(err.message, 'error');
        }
    };

    wrap.querySelector('.task-save').addEventListener('click', (e) => { e.stopPropagation(); save(); });
    wrap.querySelector('.task-cancel').addEventListener('click', (e) => { e.stopPropagation(); cancel(); });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') save();
        if (e.key === 'Escape') cancel();
    });
    input.addEventListener('click', (e) => e.stopPropagation());
}

// ----- Quick event popover -----
let quickEventCtx = null;

function openQuickEvent(mouseEvent, ctx) {
    quickEventCtx = ctx;
    const pop = document.getElementById('quick-event-popover');
    const target = document.getElementById('quick-event-target');

    let label = `Дата: ${formatDateLabel(ctx.date)}`;
    if (ctx.hour !== null && ctx.hour !== undefined) {
        label += ` · ${String(ctx.hour).padStart(2, '0')}:00`;
    }
    if (ctx.employee_name) {
        label = `${ctx.employee_name} · ${label}`;
    } else if (!ctx.employee_id) {
        label = `Выберите сотрудника · ${label}`;
    }
    target.textContent = label;

    // Позиционируем рядом с курсором
    pop.classList.remove('hidden');
    const x = Math.min(window.innerWidth - 290, mouseEvent.clientX + 8);
    const y = Math.min(window.innerHeight - 240, mouseEvent.clientY + 8);
    pop.style.left = `${x}px`;
    pop.style.top = `${y}px`;
}

function closeQuickEvent() {
    document.getElementById('quick-event-popover').classList.add('hidden');
    quickEventCtx = null;
}

async function createQuickEvent(eventType) {
    if (!quickEventCtx) return;
    let employeeId = quickEventCtx.employee_id;
    if (!employeeId) {
        // нет сотрудника — спросим первого активного как fallback (минимум кликов)
        if (state.dashboard && state.dashboard.members_diagnostics.length) {
            employeeId = state.dashboard.members_diagnostics[0].employee.id;
        } else {
            toast('Сначала выберите сотрудника', 'error');
            return;
        }
    }
    try {
        await api('/api/events/quick', {
            method: 'POST',
            body: JSON.stringify({
                employee_id: employeeId,
                event_type: eventType,
                date: quickEventCtx.date,
                hour: quickEventCtx.hour,
            }),
        });
        toast('Событие добавлено', 'success');
        closeQuickEvent();
        loadHeatmap();
        loadDashboard(state.currentTeamId);
    } catch (err) {
        toast(err.message, 'error');
    }
}

function formatDateLabel(iso) {
    if (!iso) return '';
    try {
        const d = new Date(iso);
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch (_) { return iso; }
}
