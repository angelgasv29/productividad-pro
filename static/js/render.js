/* Renderizado de todas las vistas. */
(function () {
    'use strict';

    const DAY_NAMES = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
    const MODULE_LABELS = { habits: 'Hábitos', routines: 'Rutinas', backlog: 'Backlog' };
    const PRIORITY_ORDER = { Alta: 0, Media: 1, Baja: 2 };
    const MODULE_ICONS = { habits: '🌱', routines: '🔁', backlog: '📋' };

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function $(id) { return document.getElementById(id); }

    function formatDate(value) {
        if (!value) return '';
        const text = String(value);
        const datePart = text.slice(0, 10);
        const parts = datePart.split('-');
        if (parts.length !== 3) return text;
        const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        if (Number.isNaN(date.getTime())) return datePart;
        return date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' });
    }

    function formatShortDate(value) {
        if (!value) return '';
        const text = String(value).slice(0, 10);
        const parts = text.split('-');
        if (parts.length !== 3) return text;
        const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        if (Number.isNaN(date.getTime())) return text;
        return date.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
    }

    function formatTime(value) {
        if (!value) return '';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value).slice(11, 16);
        return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    }

    function formatDateTime(value) {
        if (!value) return '';
        return `${formatDate(value)} ${formatTime(value)}`;
    }

    function durationLabel(minutes) {
        const total = Math.max(0, Math.round(Number(minutes) || 0));
        if (total < 60) return `${total} min`;
        const hours = Math.floor(total / 60);
        const rest = total % 60;
        return rest ? `${hours} h ${rest} min` : `${hours} h`;
    }

    function toDateTimeLocal(value) {
        const date = value ? new Date(value) : new Date();
        const pad = (number) => String(number).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    function todayInput() {
        const date = new Date();
        const pad = (number) => String(number).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    }

    function initials(username) {
        const value = String(username || '?').trim();
        const parts = value.split(/[\s_.-]+/).filter(Boolean);
        if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
        return value.slice(0, 2).toUpperCase();
    }

    function renderHeader() {
        const select = $('workspaceSelect');
        if (select) {
            select.innerHTML = AppState.workspaces.map((workspace) =>
                `<option value="${esc(workspace.id)}" ${workspace.id === AppState.currentWorkspaceId ? 'selected' : ''}>${esc(workspace.name)}</option>`
            ).join('');
        }
        const countdown = $('yearCountdown');
        if (countdown && AppState.yearCountdown) {
            countdown.textContent = AppState.yearCountdown.label || '';
        }
        if (AppState.user) {
            const username = AppState.user.username || '';
            const headerUsername = $('headerUsername');
            const headerAvatar = $('headerAvatar');
            if (headerUsername) headerUsername.textContent = username;
            if (headerAvatar) headerAvatar.textContent = AppState.user.initials || initials(username);
            const dropdownUsername = $('dropdownUsername');
            const dropdownEmail = $('dropdownEmail');
            if (dropdownUsername) dropdownUsername.textContent = username;
            if (dropdownEmail) dropdownEmail.textContent = AppState.user.email || '';
        }
        const theme = document.documentElement.getAttribute('data-theme');
        const themeToggle = $('themeToggle');
        if (themeToggle) themeToggle.textContent = theme === 'dark' ? '☀️' : '🌙';
    }

    function renderAll() {
        renderHeader();
        renderHabits();
        renderRoutines();
        renderBacklog();
        renderAchievementSection('habits', 'habitAchievements');
        renderAchievementSection('routines', 'routineAchievements');
        renderAchievementSection('backlog', 'backlogAchievements');
        renderExceptions();
        renderObjectives();
        renderMetrics();
        renderHistory();
        renderAchievementList();
        renderProfile();
        populateObjectiveSelects();
    }

    // ------------------------------------------------------------------
    // Árboles
    // ------------------------------------------------------------------

    function scheduleBadge(node) {
        const days = node.schedule_days || [];
        if (!days.length) return '';
        const labels = days.map((day) => DAY_NAMES[day] || '').join(' ');
        const active = node.active_today;
        return `<span class="badge-schedule ${active ? 'active-today' : 'inactive-today'}" title="Días activos">🗓️ ${esc(labels)}</span>`;
    }

    function timerBadge(node) {
        if (!node.focus_mins_today) return '';
        return `<span class="time-badge ${node.used_timer_today ? 'with-timer' : 'no-timer'}" title="Enfoque registrado hoy">⏱️ ${node.focus_mins_today}m</span>`;
    }

    function nodeBadges(node, moduleType) {
        let html = '';
        if (moduleType === 'routines' && node.routine_category) {
            html += `<span class="badge" style="background:var(--cat-${node.routine_category.toLowerCase()})">${esc(node.routine_category)}</span>`;
        }
        if (moduleType === 'backlog' && node.priority) {
            html += `<span class="badge prio-${node.priority}">${esc(node.priority)}</span>`;
        }
        if (moduleType === 'backlog' && node.tag) {
            html += `<span class="badge tag-${node.tag}">${esc(node.tag)}</span>`;
        }
        if (node.objective_id) html += `<span class="badge" style="background:var(--primary)" title="Vinculada a un objetivo">🎯</span>`;
        return html + scheduleBadge(node) + timerBadge(node);
    }

    function nodeHtml(node, moduleType) {
        const children = node.children || [];
        const isRoutine = moduleType === 'routines';
        const inactive = isRoutine && !node.active_today && (node.schedule_days || []).length;
        const classes = [
            isRoutine && node.routine_category ? `routine-${node.routine_category}` : '',
            inactive ? 'routine-inactive-today' : '',
        ].filter(Boolean).join(' ');
        const checked = node.completed ? 'checked' : '';
        const disabled = children.length ? 'disabled' : '';
        const titleClass = node.completed ? 'node-title node-completed' : 'node-title';
        const actions = [
            `<button class="icon-btn" data-action="add-subtask" data-node-id="${esc(node.id)}" data-module="${moduleType}" title="Añadir subtarea">➕</button>`,
            `<button class="icon-btn" data-action="schedule-node" data-node-id="${esc(node.id)}" title="Agendar">🗓️</button>`,
            `<button class="icon-btn" data-action="edit-node" data-node-id="${esc(node.id)}" data-module="${moduleType}" title="Editar">✏️</button>`,
            AppState.objectives.length ? `<button class="icon-btn" data-action="link-node-objective" data-node-id="${esc(node.id)}" title="Vincular a objetivo">🎯</button>` : '',
            node.completed ? `<button class="icon-btn success" data-action="archive-node" data-node-id="${esc(node.id)}" title="Archivar como logro">📦</button>` : '',
            `<button class="icon-btn danger" data-action="delete-node" data-node-id="${esc(node.id)}" title="Eliminar">🗑️</button>`,
        ].join('');
        return `
        <div class="tree-node">
            <div class="tree-node-content ${classes}" data-node-row="${esc(node.id)}">
                <input type="checkbox" class="custom-checkbox" data-toggle-node="${esc(node.id)}" ${checked} ${disabled} title="${children.length ? 'Completa las subtareas para marcar el padre' : 'Marcar completada'}">
                <span class="${titleClass}">${esc(node.title)}</span>
                ${nodeBadges(node, moduleType)}
                <span class="node-actions">${actions}</span>
            </div>
            ${children.length ? `<div class="tree-children">${children.map((child) => nodeHtml(child, moduleType)).join('')}</div>` : ''}
        </div>`;
    }

    function renderTree(moduleType, nodes, containerId) {
        const container = $(containerId);
        if (!container) return;
        if (!nodes || !nodes.length) {
            container.innerHTML = `<p class="text-sm" style="padding:.6rem 0;">Sin ${MODULE_LABELS[moduleType].toLowerCase()} todavía. Añade el primero arriba.</p>`;
            return;
        }
        container.innerHTML = nodes.map((node) => nodeHtml(node, moduleType)).join('');
    }

    function renderHabits() {
        renderTree('habits', AppState.nodes.habits, 'habitTree');
    }

    function renderRoutines() {
        renderTree('routines', AppState.nodes.routines, 'routineTree');
    }

    function filteredBacklog() {
        const tag = ($('filterTag') || {}).value || '';
        const priority = ($('filterPriority') || {}).value || '';
        const sort = ($('sortBacklog') || {}).value || 'default';
        const mapNodes = (nodes) => nodes.map((node) => ({ ...node, children: mapNodes(node.children || []) }));
        let roots = mapNodes(AppState.nodes.backlog || []);
        if (tag) roots = roots.filter((node) => node.tag === tag);
        if (priority) roots = roots.filter((node) => node.priority === priority);
        if (sort === 'prio-desc') {
            roots.sort((a, b) => (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9));
        } else if (sort === 'prio-asc') {
            roots.sort((a, b) => (PRIORITY_ORDER[b.priority] ?? 9) - (PRIORITY_ORDER[a.priority] ?? 9));
        } else if (sort === 'name-asc') {
            roots.sort((a, b) => String(a.title).localeCompare(String(b.title), 'es'));
        }
        return roots;
    }

    function renderBacklog() {
        renderTree('backlog', filteredBacklog(), 'backlogTree');
    }

    function renderAchievementSection(moduleType, containerId) {
        const container = $(containerId);
        if (!container) return;
        const items = (AppState.achievements || []).filter((item) => item.module_type === moduleType).slice(0, 5);
        if (!items.length) {
            container.innerHTML = '';
            return;
        }
        container.innerHTML = `
            <button class="ach-toggle" data-action="toggle-achievements">
                <span>🏆 Logros recientes · ${MODULE_LABELS[moduleType]} (${items.length})</span><span>▾</span>
            </button>
            <div class="ach-body">
                ${items.map((item) => `
                    <div class="ach-item">
                        <span>${item.timer_mins ? '⏱️' : '✅'}</span>
                        <span>${esc(item.title)}</span>
                        <span class="ach-meta">${formatDate(item.completed_at)}${item.timer_mins ? ` · ${item.timer_mins} min` : ''}</span>
                    </div>`).join('')}
            </div>`;
    }

    // ------------------------------------------------------------------
    // Timeline y timer
    // ------------------------------------------------------------------

    async function loadTimeline() {
        try {
            const data = await Api.get(`/schedule/timeline?workspace_id=${encodeURIComponent(AppState.currentWorkspaceId)}`, { silent: true });
            AppState.timeline = data;
            renderTimeline();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function renderTimeline() {
        const container = $('timeline');
        if (!container) return;
        const data = AppState.timeline;
        if (!data || !data.hours) {
            container.innerHTML = '<p class="text-sm">Cargando línea de tiempo…</p>';
            return;
        }
        container.innerHTML = data.hours.map((hour) => {
            const tasks = hour.tasks || [];
            const exception = hour.exception;
            const taskHtml = tasks.map((task) => `
                <div class="scheduled-task ${hour.is_current ? 'focus-current' : ''}">
                    <input type="checkbox" class="custom-checkbox" data-toggle-node="${esc(task.node_id)}" ${task.completed ? 'checked' : ''} title="Completar">
                    <span class="${task.completed ? 'node-completed' : ''}" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                        ${MODULE_ICONS[task.module_type] || '•'} ${esc(task.title)}
                        ${task.timer_secs_today ? `<span class="time-badge with-timer">⏱️ ${Math.round(task.timer_secs_today / 60)}m</span>` : ''}
                        ${task.recurring ? '<span class="sched-badge sched-rec">rec</span>' : '<span class="sched-badge sched-once">única</span>'}
                    </span>
                    <button class="icon-btn" data-action="link-timer-node" data-node-id="${esc(task.node_id)}" title="Vincular al timer">⏱️</button>
                    <button class="icon-btn danger" data-action="unassign-slot" data-slot-id="${esc(task.slot_id)}" title="Quitar de esta hora">✕</button>
                </div>`).join('');
            return `
            <div class="time-block ${hour.is_current ? 'active-focus' : ''} ${hour.is_night ? 'night-block' : ''}">
                <div class="time-label" style="display:flex;justify-content:space-between;align-items:center;">
                    <span>${hour.is_night ? '🌙 ' : ''}${esc(hour.hour_slot)}</span>
                    <button class="icon-btn" data-action="assign-hour" data-hour="${esc(hour.hour_slot)}" title="Agendar tarea en esta hora">＋</button>
                </div>
                ${exception ? `<div class="schedule-exception exc-${esc(exception.impact)}"><span>⚡ ${esc(exception.title)}</span><span class="badge prio-${exception.impact === 'Alta' ? 'Alta' : 'Media'}">${esc(exception.impact)}</span></div>` : ''}
                ${taskHtml || '<div class="text-sm" style="padding:.2rem .4rem;opacity:.55;">Libre</div>'}
            </div>`;
        }).join('');
    }

    // ------------------------------------------------------------------
    // Excepciones
    // ------------------------------------------------------------------

    async function loadExceptions() {
        try {
            const data = await Api.get('/exceptions', { silent: true });
            AppState.exceptionsAll = data.items || [];
            AppState.exceptionAreas = data.areas || [];
            renderExceptions();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function renderExceptions() {
        const areasContainer = $('exceptionAreas');
        const listContainer = $('exceptionList');
        if (!areasContainer || !listContainer) return;
        const areas = AppState.exceptionAreas || [];
        areasContainer.innerHTML = areas.length ? areas.map((area) => `
            <div class="metric-card" style="padding:1rem;text-align:left;">
                <div class="text-sm">${esc(area.area || 'General')}</div>
                <div style="font-size:1.4rem;font-weight:800;">${area.count}</div>
                <div class="text-sm">${durationLabel(area.minutes)} de fuga</div>
            </div>`).join('') : '<p class="text-sm">Sin excepciones registradas.</p>';

        const items = AppState.exceptionsAll || AppState.exceptions || [];
        if (!items.length) {
            listContainer.innerHTML = '<p class="text-sm">Todavía no registraste ninguna fuga de tiempo.</p>';
            return;
        }
        listContainer.innerHTML = items.slice().reverse().map((item) => {
            const minutes = item.start_time && item.end_time
                ? (new Date(item.end_time) - new Date(item.start_time)) / 60000
                : 0;
            return `
            <div class="exception-item exception-impact-${esc(item.impact)}">
                <div style="display:flex;justify-content:space-between;gap:.5rem;align-items:flex-start;flex-wrap:wrap;">
                    <div>
                        <strong>${esc(item.title)}</strong>
                        <span class="badge prio-${item.impact === 'Alta' ? 'Alta' : 'Media'}">${esc(item.impact)}</span>
                        ${item.area ? `<span class="badge" style="background:var(--text-muted)">${esc(item.area)}</span>` : ''}
                    </div>
                    <button class="icon-btn danger" data-action="delete-exception" data-exception-id="${esc(item.id)}" title="Eliminar excepción">🗑️</button>
                </div>
                <div class="text-sm" style="margin-top:.35rem;">
                    ${formatDateTime(item.start_time)} → ${formatTime(item.end_time)} · ${durationLabel(minutes)}
                    ${item.workspace_name ? ` · ${esc(item.workspace_name)}` : ''}
                    ${item.blocked_task_ids && item.blocked_task_ids.length ? ` · bloqueó ${item.blocked_task_ids.length} tarea(s)` : ''}
                </div>
                ${item.note ? `<div class="text-sm" style="margin-top:.25rem;">📝 ${esc(item.note)}</div>` : ''}
            </div>`;
        }).join('');
    }

    // ------------------------------------------------------------------
    // Objetivos
    // ------------------------------------------------------------------

    function horizonLabel(horizon) {
        return String(horizon || '').charAt(0).toUpperCase() + String(horizon || '').slice(1);
    }

    function renderObjectives() {
        const container = $('objectiveList');
        if (!container) return;
        if (!AppState.objectives.length) {
            container.innerHTML = '<p class="text-sm">Sin objetivos todavía. Crea uno para medir tu avance.</p>';
            return;
        }
        container.innerHTML = AppState.objectives.map((objective) => `
            <div class="obj-card">
                <div class="obj-header">
                    <div style="flex:1;">
                        <strong style="font-size:1.05rem;">${esc(objective.title)}</strong>
                        <div class="text-sm" style="margin-top:.2rem;">
                            ${objective.description ? esc(objective.description) + ' · ' : ''}
                            ${objective.start_date ? formatDate(objective.start_date) : 'Sin inicio'}
                            ${objective.end_date ? ` → ${formatDate(objective.end_date)}` : ''}
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;">
                        <span class="obj-horizon">${esc(horizonLabel(objective.horizon))}</span>
                        <button class="icon-btn" data-action="objective-link" data-objective-id="${esc(objective.id)}" title="Vincular tarea">🔗</button>
                        <button class="icon-btn danger" data-action="delete-objective" data-objective-id="${esc(objective.id)}" title="Eliminar objetivo">🗑️</button>
                    </div>
                </div>
                <div class="obj-pbar"><div class="obj-pfill" style="width:${objective.pct}%"></div></div>
                <div class="text-sm">${objective.done}/${objective.total} tareas · ${objective.pct}% completado</div>
                <div class="obj-linked">
                    ${(objective.links || []).map((link) => `
                        <div class="obj-linked-item ${link.done ? 'done' : ''}">
                            <span>${link.module_type ? (MODULE_ICONS[link.module_type] || '•') : '•'}</span>
                            <span style="flex:1;">${esc(link.title)}</span>
                            ${link.archived ? '<span class="text-sm">archivada</span>' : ''}
                            <button class="icon-btn danger" data-action="unlink-objective" data-objective-id="${esc(objective.id)}" data-node-id="${esc(link.node_id)}" title="Desvincular">✕</button>
                        </div>`).join('') || '<span class="text-sm">Sin tareas vinculadas.</span>'}
                </div>
            </div>`).join('');
    }

    function populateObjectiveSelects() {
        const options = '<option value="">Sin objetivo</option>' + AppState.objectives.map((objective) =>
            `<option value="${esc(objective.id)}">${esc(objective.title)}</option>`
        ).join('');
        const editObjective = $('editObjective');
        if (editObjective) editObjective.innerHTML = options;
        const linkObjectiveSelect = $('linkObjectiveSelect');
        if (linkObjectiveSelect) linkObjectiveSelect.innerHTML = AppState.objectives.map((objective) =>
            `<option value="${esc(objective.id)}">${esc(objective.title)}</option>`
        ).join('');
        const taskSelect = $('linkObjectiveTaskSelect');
        if (taskSelect) {
            const tasks = State.linkableTasks();
            taskSelect.innerHTML = tasks.length
                ? tasks.map((node) => `<option value="${esc(node.id)}">${esc(node.title)} · ${MODULE_LABELS[node.module_type] || node.module_type}</option>`).join('')
                : '<option value="">No hay tareas disponibles</option>';
        }
    }

    // ------------------------------------------------------------------
    // Métricas
    // ------------------------------------------------------------------

    function renderMetrics() {
        renderTodayScore();
        renderGlobalStats();
        renderHeatmap();
        renderTimerImpact();
        renderCorrelation();
    }

    function renderTodayScore() {
        const container = $('todayScoreCard');
        if (!container) return;
        const score = AppState.todayScore;
        if (!score) {
            container.innerHTML = '<p class="text-sm">Sin datos de score todavía.</p>';
            return;
        }
        const breakdown = score.breakdown || {};
        const globalScore = score.global_score || {};
        const bar = (label, completed, total, color) => {
            const pct = total ? Math.round(completed / total * 100) : 0;
            return `<div style="margin-top:.55rem;">
                <div style="display:flex;justify-content:space-between;font-size:.75rem;color:var(--text-muted);"><span>${label}</span><span>${completed}/${total}</span></div>
                <div class="score-track"><div class="score-fill" style="width:${pct}%;background:${color}"></div></div>
            </div>`;
        };
        container.innerHTML = `
            <div class="progress-circle" style="background:conic-gradient(var(--primary) ${score.score}%, var(--border) 0%);">
                <div class="progress-inner">${score.score}</div>
            </div>
            <div style="flex:1;min-width:230px;">
                <h3>Score de hoy · ${esc(score.workspace_name || State.workspaceName(score.workspace_id))}</h3>
                <p class="text-sm">Global de todos los espacios: <strong>${globalScore.score || 0}/100</strong> · Corte lógico: ${esc(AppState.logicalDate)}</p>
                ${bar('Hábitos', breakdown.h_comp || 0, breakdown.h_total || 0, 'var(--success)')}
                ${bar('Rutinas', breakdown.r_comp || 0, breakdown.r_total || 0, 'var(--primary)')}
                ${bar('Backlog', breakdown.b_comp || 0, breakdown.b_total || 0, 'var(--warning)')}
                ${breakdown.penalty ? `<p class="text-sm" style="margin-top:.5rem;color:var(--danger);">⚡ Penalización por excepciones: −${breakdown.penalty} pts (${breakdown.exc_mins || 0} min)</p>` : ''}
            </div>`;
    }

    function renderGlobalStats() {
        const container = $('globalStatsGrid');
        if (!container) return;
        const stats = AppState.globalStats || {};
        const cards = [
            ['Días registrados', stats.dias_totales ?? 0, '📅'],
            ['Score promedio', `${stats.score_promedio_global ?? 0}/100`, '⭐'],
            ['Promedio 7 días', `${stats.score_prom_7d ?? 0}/100`, '📈'],
            ['Promedio 30 días', `${stats.score_prom_30d ?? 0}/100`, '📊'],
            ['Racha actual', `${stats.racha_actual ?? 0} días`, '🔥'],
            ['Racha máxima', `${stats.racha_maxima ?? 0} días`, '🏅'],
            ['Hábitos completados', stats.total_habitos_comp ?? 0, '🌱'],
            ['Rutinas completadas', stats.total_rutinas_comp ?? 0, '🔁'],
            ['Backlog completado', stats.total_backlog_comp ?? 0, '📋'],
            ['Minutos de fuga', stats.total_minutos_fuga ?? 0, '⚡'],
        ];
        container.innerHTML = cards.map(([label, value, icon]) => `
            <div class="metric-card" style="padding:1.2rem;text-align:left;">
                <div class="text-sm">${icon} ${label}</div>
                <div style="font-size:1.55rem;font-weight:800;margin-top:.25rem;">${esc(value)}</div>
            </div>`).join('');
    }

    function renderHeatmap() {
        const container = $('heatmap');
        if (!container) return;
        const data = AppState.heatmap;
        if (!data || !data.weeks) {
            container.innerHTML = '<p class="text-sm">Cargando mapa de calor…</p>';
            return;
        }
        const weeks = data.weeks;
        container.innerHTML = `
            <div style="display:flex;gap:6px;align-items:flex-start;">
                <div style="display:grid;grid-template-rows:repeat(7,14px);gap:3px;font-size:.6rem;color:var(--text-muted);padding-top:16px;">
                    ${['D', 'L', 'M', 'X', 'J', 'V', 'S'].map((day) => `<span style="height:14px;line-height:14px;">${day}</span>`).join('')}
                </div>
                <div>
                    <div style="display:flex;gap:3px;margin-bottom:3px;font-size:.6rem;color:var(--text-muted);">
                        ${data.month_labels.map((label) => `<span style="min-width:14px;">${esc(label)}</span>`).join('')}
                    </div>
                    <div style="display:flex;gap:3px;">
                        ${weeks.map((week) => `<div style="display:grid;grid-template-rows:repeat(7,14px);gap:3px;">${week.map((cell) => `
                            <div class="heatmap-cell" data-score="${cell.level}" title="${esc(cell.tooltip || cell.date)}"></div>`).join('')}</div>`).join('')}
                    </div>
                </div>
            </div>`;
    }

    function renderTimerImpact() {
        const container = $('timerImpact');
        if (!container) return;
        const data = AppState.timerImpact;
        if (!data) {
            container.innerHTML = '<p class="text-sm">Cargando impacto del timer…</p>';
            return;
        }
        container.innerHTML = `
            <div class="metrics-grid" style="grid-template-columns:repeat(3,1fr);gap:.6rem;">
                <div class="metric-card" style="padding:.8rem;"><div class="text-sm">Con timer</div><div style="font-size:1.4rem;font-weight:800;">${data.with_timer_count}</div></div>
                <div class="metric-card" style="padding:.8rem;"><div class="text-sm">Sin timer</div><div style="font-size:1.4rem;font-weight:800;">${data.without_timer_count}</div></div>
                <div class="metric-card" style="padding:.8rem;"><div class="text-sm">Adopción</div><div style="font-size:1.4rem;font-weight:800;">${data.adoption_pct}%</div></div>
            </div>
            <p class="text-sm" style="margin-top:.6rem;">Enfoque promedio: <strong>${data.avg_focus_mins} min</strong> · ${data.total_completed} tareas completadas.</p>
            ${(data.last_with_timer || []).slice(0, 5).map((item) => `<div class="ach-item"><span>⏱️</span><span>${esc(item.title)}</span><span class="ach-meta">${item.timer_mins} min · ${formatDate(item.completed_at)}</span></div>`).join('')}`;
    }

    function renderCorrelation() {
        const container = $('correlation');
        if (!container) return;
        const data = AppState.correlation;
        if (!data) {
            container.innerHTML = '<p class="text-sm">Cargando correlación…</p>';
            return;
        }
        container.innerHTML = `
            <div class="correlation-box">
                <strong>${data.total_exceptions}</strong> excepciones · <strong>${data.high_impact_exceptions}</strong> de impacto alto
            </div>
            ${(data.suggestions || []).map((suggestion) => `<div class="suggestion-item">💡 ${esc(suggestion)}</div>`).join('') || '<p class="text-sm">Aún no hay suficientes datos para sugerencias.</p>'}
            ${(data.days || []).slice(-7).reverse().map((day) => `<div class="ach-item"><span>${day.exception_count ? '⚡' : '✅'}</span><span>${formatDate(day.date)}</span><span class="ach-meta">score ${day.score} · ${day.exception_count} exc · ${Math.round(day.total_minutes)} min</span></div>`).join('')}`;
    }

    // ------------------------------------------------------------------
    // Logros
    // ------------------------------------------------------------------

    function achievementRow(item) {
        return `<div class="ach-item">
            <span>${item.timer_mins ? '⏱️' : '✅'}</span>
            <span style="flex:1;">${esc(item.title)}</span>
            ${item.workspace_name ? `<span class="text-sm">${esc(item.workspace_name)}</span>` : ''}
            <span class="badge" style="background:var(--primary)">${MODULE_LABELS[item.module_type] || item.module_type}</span>
            <span class="ach-meta">${formatDate(item.completed_at)}${item.timer_mins ? ` · ${item.timer_mins} min` : ''}</span>
        </div>`;
    }

    async function loadAchievements() {
        try {
            const params = new URLSearchParams({
                limit: String(AppState.achievementsLimit),
                offset: String(AppState.achievementsPage * AppState.achievementsLimit),
            });
            const moduleType = ($('achModule') || {}).value || '';
            const timer = ($('achTimer') || {}).value || '';
            const search = ($('achSearch') || {}).value || '';
            if (moduleType) params.set('module_type', moduleType);
            if (timer) params.set('timer', timer);
            if (search) params.set('search', search);
            const data = await Api.get(`/achievements?${params.toString()}`, { silent: true });
            AppState.achievementsFull = data;
            renderAchievementList();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function renderAchievementList() {
        const container = $('achievementList');
        if (!container) return;
        const data = AppState.achievementsFull;
        const items = data ? data.items : (AppState.achievements || []);
        const total = data ? data.total : (AppState.achievementTotal || 0);
        if (!items.length) {
            container.innerHTML = '<p class="text-sm">No hay logros que coincidan con el filtro.</p>';
        } else {
            container.innerHTML = items.map(achievementRow).join('');
        }
        const info = $('achPageInfo');
        if (info) {
            const page = AppState.achievementsPage + 1;
            const pages = Math.max(1, Math.ceil(total / AppState.achievementsLimit));
            info.textContent = `Página ${page} de ${pages} · ${total} logros`;
        }
        const prev = $('achPrevBtn');
        const next = $('achNextBtn');
        if (prev) prev.disabled = AppState.achievementsPage <= 0;
        if (next) next.disabled = !data || !data.has_more;
    }

    // ------------------------------------------------------------------
    // Historial
    // ------------------------------------------------------------------

    async function loadHistory() {
        try {
            const params = new URLSearchParams({
                period: AppState.historyPeriod,
                limit: '30',
                offset: String(AppState.historyOffset),
            });
            const data = await Api.get(`/analytics/history?${params.toString()}`, { silent: true });
            AppState.history = data;
            renderHistory();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function historyTaskRow(item, icon) {
        return `<div class="history-task-row ${item.completed ? 'history-task-done' : 'history-task-fail'}">
            <span>${item.completed ? '✅' : '○'}</span>
            <span>${icon} ${esc(item.title)}${item.parent_title ? ` <span class="text-sm">(${esc(item.parent_title)})</span>` : ''}</span>
        </div>`;
    }

    function historyDay(day) {
        const summary = day.summary || {};
        const exceptions = (day.exceptions || []).map((item) => `
            <div class="history-exc-row ${item.impact === 'Leve' ? 'leve' : ''}">
                ⚡ <strong>${esc(item.title)}</strong> · ${esc(item.impact)}
                ${item.start_time ? ` · ${formatTime(item.start_time)}–${formatTime(item.end_time)}` : ''}
            </div>`).join('');
        return `<div class="history-day">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.4rem;margin-bottom:.3rem;">
                <strong>${formatDate(day.date)}</strong>
                <span class="text-sm">
                    ${day.score == null ? 'Sin score' : `Score ${day.score}`}
                    ${day.fallback ? ' · <span title="Reconstruido desde scores y logros">datos legacy</span>' : ''}
                    ${summary.completed != null ? ` · ${summary.completed}/${summary.total} tareas` : ''}
                </span>
            </div>
            ${(day.habits || []).map((item) => historyTaskRow(item, '🌱')).join('')}
            ${(day.routines || []).map((item) => historyTaskRow(item, '🔁')).join('')}
            ${(day.backlog || []).map((item) => historyTaskRow(item, '📋')).join('')}
            ${exceptions}
            ${(day.achievements || []).length ? `<div class="text-sm" style="margin-top:.3rem;">🏆 ${day.achievements.map((item) => esc(item.title)).join(' · ')}</div>` : ''}
        </div>`;
    }

    function renderHistory() {
        const container = $('historyList');
        if (!container) return;
        const data = AppState.history;
        if (!data) {
            container.innerHTML = '<p class="text-sm">Cargando historial…</p>';
            return;
        }
        if (!data.items.length) {
            container.innerHTML = '<p class="text-sm">Todavía no hay días registrados para este período.</p>';
        } else {
            container.innerHTML = data.items.map((bucket, index) => `
                <div class="history-card" data-history-index="${index}">
                    <div class="history-card-header" data-action="toggle-history" data-index="${index}">
                        <div>
                            <strong>${esc(bucket.title)}</strong>
                            <span class="text-sm">${esc(bucket.subtitle)}</span>
                        </div>
                        <div class="history-card-summary">
                            <span>⭐ ${bucket.score_avg == null ? '—' : bucket.score_avg}</span>
                            <span>✅ ${bucket.completed}/${bucket.total}</span>
                            <span>⚡ ${bucket.fuga} min</span>
                            <span>▾</span>
                        </div>
                    </div>
                    <div class="history-card-body">
                        ${bucket.days.map(historyDay).join('')}
                    </div>
                </div>`).join('');
        }
        const info = $('historyPageInfo');
        if (info) {
            const pages = Math.max(1, Math.ceil(data.total / data.limit));
            const page = Math.floor(data.offset / data.limit) + 1;
            info.textContent = `Página ${page} de ${pages} · ${data.total} períodos`;
        }
        const prev = $('historyPrevBtn');
        const next = $('historyNextBtn');
        if (prev) prev.disabled = data.offset <= 0;
        if (next) next.disabled = !data.has_more;
    }

    // ------------------------------------------------------------------
    // Perfil
    // ------------------------------------------------------------------

    function renderProfile() {
        const user = AppState.user;
        if (!user) return;
        const setValue = (id, value) => {
            const element = $(id);
            if (element && document.activeElement !== element) element.value = value == null ? '' : value;
        };
        setValue('profileUsername', user.username);
        setValue('profileEmail', user.email);
        setValue('profileTheme', user.theme || 'light');
        setValue('profileCutoff', user.logical_cutoff_hour);
        setValue('profileWork', user.preferences ? user.preferences.pomodoro_work_min : 25);
        setValue('profileBreak', user.preferences ? user.preferences.pomodoro_break_min : 5);
        const created = $('profileCreated');
        if (created) created.textContent = `Cuenta creada el ${formatDate(user.created_at)}`;
    }

    window.Render = {
        esc,
        formatDate,
        formatShortDate,
        formatTime,
        formatDateTime,
        durationLabel,
        toDateTimeLocal,
        todayInput,
        initials,
        renderHeader,
        renderAll,
        renderHabits,
        renderRoutines,
        renderBacklog,
        renderTree,
        renderExceptions,
        renderObjectives,
        renderMetrics,
        renderHeatmap,
        renderTimerImpact,
        renderCorrelation,
        renderAchievementList,
        renderHistory,
        renderProfile,
        renderTimeline,
        loadTimeline,
        loadExceptions,
        loadAchievements,
        loadHistory,
        populateObjectiveSelects,
        MODULE_LABELS,
        DAY_NAMES,
    };
})();
