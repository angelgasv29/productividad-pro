/* Timer Pro: UI, cuenta atrás local y sincronización con el servidor. */
(function () {
    'use strict';

    let tickHandle = null;
    let pollHandle = null;
    let endsAt = null;
    let finishedHandled = false;
    let selectedMode = 'pomodoro';

    function $id(id) { return document.getElementById(id); }

    function formatSeconds(total) {
        const value = Math.max(0, Math.round(Number(total) || 0));
        const minutes = Math.floor(value / 60);
        const seconds = value % 60;
        return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    function isBreak(state) {
        return state && state.phase === 'break';
    }

    function currentRemaining() {
        if (!AppState.timer) return 0;
        if (AppState.timer.running && endsAt) {
            return Math.max(0, Math.round((endsAt - Date.now()) / 1000));
        }
        return Math.max(0, Number(AppState.timer.remaining_secs) || 0);
    }

    async function refreshState() {
        try {
            const state = await Api.get('/timer/state', { silent: true });
            applyState(state);
            return state;
        } catch (error) {
            return null;
        }
    }

    function applyState(state, notify = true) {
        const previous = AppState.timer;
        AppState.timer = state;
        if (state.running) {
            endsAt = Date.now() + Math.max(0, Number(state.remaining_secs) || 0) * 1000;
            finishedHandled = false;
        } else {
            endsAt = null;
        }
        selectedMode = state.mode || 'pomodoro';
        if (notify && previous && previous.phase !== state.phase && !state.running) {
            showSessionDone(state);
        }
        render();
    }

    function render() {
        const state = AppState.timer;
        if (!state) return;
        const display = $id('timerDisplay');
        const phase = $id('timerPhase');
        const ring = $id('timerRingFill');
        const remaining = currentRemaining();
        const total = Math.max(1, Number(state.total_secs) || 1);
        if (display) {
            display.textContent = formatSeconds(remaining);
            display.classList.toggle('break-mode', isBreak(state));
            display.classList.toggle('warning-mode', remaining > 0 && remaining <= 10);
        }
        if (phase) phase.textContent = isBreak(state) ? 'DESCANSO' : 'ENFOQUE';
        if (ring) {
            const circumference = 2 * Math.PI * 65;
            ring.style.strokeDashoffset = String(circumference * (1 - remaining / total));
            ring.classList.toggle('break-mode', isBreak(state));
        }
        document.querySelectorAll('[data-timer-mode]').forEach((button) => {
            button.classList.toggle('active', button.dataset.timerMode === selectedMode);
        });
        const workInput = $id('timerWorkMin');
        const breakInput = $id('timerBreakMin');
        if (workInput && document.activeElement !== workInput) workInput.value = state.work_min;
        if (breakInput && document.activeElement !== breakInput) breakInput.value = state.break_min;

        const startBtn = $id('timerStartBtn');
        if (startBtn) {
            const pausedMid = !state.running && state.remaining_secs > 0 && state.remaining_secs < state.total_secs;
            startBtn.textContent = state.running ? '▶ En marcha' : (pausedMid ? '▶ Reanudar' : '▶ Iniciar');
            startBtn.disabled = state.running;
        }
        const pauseBtn = $id('timerPauseBtn');
        if (pauseBtn) pauseBtn.disabled = !state.running;
        const skipBtn = $id('timerSkipBtn');
        if (skipBtn) skipBtn.disabled = state.running;

        const linked = $id('timerLinkedTask');
        const linkedTitle = $id('timerLinkedTitle');
        if (linked) linked.classList.toggle('hidden', !state.node_id);
        if (linkedTitle) linkedTitle.textContent = state.node_title || '';
        const completeBtn = $id('timerCompleteTaskBtn');
        if (completeBtn) completeBtn.disabled = !state.node_id;

        const bar = $id('timerSessionBar');
        if (bar) {
            const pct = Math.min(100, Math.max(0, (Number(state.focused_secs || 0) / total) * 100));
            bar.style.width = `${pct}%`;
        }
        const cycles = $id('timerCycles');
        if (cycles) cycles.textContent = `${state.cycle_count || 0} ciclos completados · ${state.focused_secs || 0}s de enfoque en esta fase`;
    }

    async function start() {
        const workInput = $id('timerWorkMin');
        const breakInput = $id('timerBreakMin');
        const work = Math.max(1, Math.min(120, Number(workInput ? workInput.value : 25) || 25));
        const rest = Math.max(1, Math.min(60, Number(breakInput ? breakInput.value : 5) || 5));
        const state = AppState.timer;
        const pausedMid = state && !state.running && state.remaining_secs > 0 && state.remaining_secs < state.total_secs;
        const breakReady = state && !state.running && state.phase === 'break' && state.remaining_secs === state.total_secs;
        let nodeId = state ? state.node_id : null;
        if (!nodeId) {
            try {
                const suggestion = await Api.get(`/schedule/suggestion?workspace_id=${encodeURIComponent(AppState.currentWorkspaceId)}`, { silent: true });
                if (suggestion && suggestion.node_id) {
                    nodeId = suggestion.node_id;
                    showToast(`Sugerencia vinculada: ${suggestion.title}`, 'info', 3500);
                }
            } catch (_) { /* sin sugerencia */ }
        }
        try {
            const response = await Api.post('/timer/start', {
                work_min: work,
                break_min: rest,
                mode: selectedMode,
                node_id: nodeId,
                resume: Boolean(pausedMid || breakReady),
            });
            applyState(response.state);
            if (response.message) showToast(response.message, 'success');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function pause() {
        try {
            const response = await Api.post('/timer/pause', {});
            applyState(response.state);
            if (response.phase_finished) {
                showSessionDone(response.state, response.message);
            } else {
                showToast(response.message || 'Temporizador pausado.');
            }
            await State.refreshAll();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function reset() {
        try {
            const response = await Api.post('/timer/reset', {});
            applyState(response.state, false);
            showToast(response.message || 'Temporizador reiniciado.');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function skip() {
        try {
            const response = await Api.post('/timer/skip', {});
            applyState(response.state, false);
            showToast(response.message || 'Fase saltada.');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function link(nodeId) {
        try {
            const state = await Api.post('/timer/link', { node_id: nodeId });
            applyState(state);
            State.closeModal('timerLinkModal');
            showToast('Tarea vinculada al temporizador.');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function unlink() {
        try {
            const state = await Api.post('/timer/unlink', {});
            applyState(state);
            showToast('Tarea desvinculada.');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function completeTask() {
        try {
            const response = await Api.post('/timer/complete-task', {});
            applyState(response.state);
            showToast(response.message || 'Tarea completada.');
            await State.refreshAll();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function openLinkModal() {
        const select = $id('timerLinkSelect');
        if (!select) return;
        const nodes = State.pendingLeaves();
        if (!nodes.length) {
            showToast('No hay tareas hoja pendientes para vincular.', 'info');
            return;
        }
        select.innerHTML = nodes.map((node) =>
            `<option value="${Render.esc(node.id)}">${Render.esc(node.title)} · ${Render.MODULE_LABELS[node.module_type] || node.module_type}</option>`
        ).join('');
        State.openModal('timerLinkModal');
    }

    function showSessionDone(state, message) {
        const modal = $id('sessionDoneModal');
        if (!modal || modal.classList.contains('active')) return;
        const title = $id('sessionDoneTitle');
        const text = $id('sessionDoneMessage');
        const breakNext = isBreak(state);
        if (title) title.textContent = breakNext ? '¡Enfoque completado!' : '¡Descanso completado!';
        if (text) {
            text.textContent = message || (breakNext
                ? 'Tómate un descanso. La siguiente fase no se inicia automáticamente.'
                : 'Vuelve al trabajo cuando estés listo. La siguiente fase no se inicia automáticamente.');
        }
        State.openModal('sessionDoneModal');
    }

    async function nextPhase() {
        State.closeModal('sessionDoneModal');
        const state = AppState.timer;
        if (!state) return;
        try {
            const response = await Api.post('/timer/start', {
                work_min: Number(state.work_min) || 25,
                break_min: Number(state.break_min) || 5,
                mode: state.mode || selectedMode,
                node_id: state.node_id,
                resume: true,
            });
            applyState(response.state);
            showToast(response.message || 'Siguiente fase iniciada.');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function tick() {
        if (!AppState.timer) return;
        render();
        if (AppState.timer.running && currentRemaining() <= 0 && !finishedHandled) {
            finishedHandled = true;
            setTimeout(async () => {
                const state = await refreshState();
                if (state && !state.running) {
                    showSessionDone(state);
                }
            }, 400);
        }
    }

    function startPolling() {
        if (tickHandle) clearInterval(tickHandle);
        if (pollHandle) clearInterval(pollHandle);
        tickHandle = setInterval(tick, 1000);
        pollHandle = setInterval(async () => {
            if (document.visibilityState === 'visible') await refreshState();
        }, 30000);
        document.addEventListener('visibilitychange', async () => {
            if (document.visibilityState === 'visible') await refreshState();
        });
    }

    window.TimerUI = {
        refreshState,
        applyState,
        render,
        start,
        pause,
        reset,
        skip,
        link,
        unlink,
        completeTask,
        openLinkModal,
        nextPhase,
        startPolling,
        setMode: (mode) => { selectedMode = mode; render(); },
        showSessionDone,
    };
})();
