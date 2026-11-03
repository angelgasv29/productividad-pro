/* Punto de entrada: eventos, navegación y operaciones de la interfaz. */
(function () {
    'use strict';

    function $id(id) { return document.getElementById(id); }

    let searchTimer = null;

    async function init() {
        let storedTheme = 'light';
        try { storedTheme = localStorage.getItem('prodpro-theme') || 'light'; } catch (_) { /* ignore */ }
        State.applyTheme(storedTheme, false);

        bindEvents();
        setDefaultExceptionTimes();

        try {
            await State.loadBootstrap();
            Render.renderAll();
            await TimerUI.refreshState();
            TimerUI.render();
            TimerUI.startPolling();
            await refreshDbStatus();
        } catch (error) {
            showToast(error.message || 'No se pudo cargar la aplicación.', 'error', 5000);
        }
    }

    function activateModule(module) {
        AppState.activeModule = module;
        document.querySelectorAll('.nav-btn').forEach((button) => {
            button.classList.toggle('active', button.dataset.module === module);
        });
        document.querySelectorAll('.module').forEach((section) => {
            section.classList.toggle('active', section.id === `mod-${module}`);
        });
        if (module === 'metrics' && window.Analytics) Analytics.refresh();
        if (module === 'backlog') Render.loadTimeline();
        if (module === 'exceptions') Render.loadExceptions();
        if (module === 'achievements') Render.loadAchievements();
        if (module === 'history') Render.loadHistory();
        if (module === 'profile') Render.renderProfile();
    }

    function setDefaultExceptionTimes() {
        const end = new Date();
        const start = new Date(end.getTime() - 30 * 60 * 1000);
        const startInput = $id('exceptionStart');
        const endInput = $id('exceptionEnd');
        if (startInput && !startInput.value) startInput.value = Render.toDateTimeLocal(start);
        if (endInput && !endInput.value) endInput.value = Render.toDateTimeLocal(end);
    }

    async function refreshDbStatus() {
        try {
            const health = await Api.get('/system/health', { silent: true });
            const dot = $id('dbDot');
            const text = $id('dbStatusText');
            if (dot) dot.classList.toggle('offline', !health.ok);
            if (text) text.textContent = health.ok
                ? `SQLite OK · ${health.counts.nodes} nodos · ${(health.database_bytes / 1024).toFixed(1)} KB`
                : 'Base de datos con problemas';
            AppState.health = health;
        } catch (_) {
            const dot = $id('dbDot');
            const text = $id('dbStatusText');
            if (dot) dot.classList.add('offline');
            if (text) text.textContent = 'No se pudo comprobar la base de datos';
        }
    }

    async function showHealth() {
        try {
            const health = await Api.get('/system/health', { silent: true });
            AppState.health = health;
            const container = $id('healthContent');
            if (container) {
                const counts = Object.entries(health.counts || {})
                    .map(([key, value]) => `<div style="display:flex;justify-content:space-between;border-bottom:1px dashed var(--border);padding:.25rem 0;"><span>${Render.esc(key)}</span><strong>${Render.esc(value)}</strong></div>`)
                    .join('');
                const backups = Object.entries(health.backups || {})
                    .map(([slot, info]) => `<div style="margin-top:.4rem;">Slot ${Render.esc(slot)}: ${info.exists ? `${info.bytes} bytes · ${Render.esc(info.modified_at || '')}` : 'vacío'}</div>`)
                    .join('');
                container.innerHTML = `
                    <p><strong>${Render.esc(health.user)}</strong> · ${Render.esc(health.server_time)}</p>
                    <p>Base de datos: <code>${Render.esc(health.database_path)}</code> (${health.database_bytes} bytes)</p>
                    <p>Fecha lógica: <strong>${Render.esc(health.logical_date)}</strong> · Esquema v${health.schema_version}</p>
                    <div style="margin-top:.7rem;">${counts}</div>
                    <div style="margin-top:.7rem;">${backups}</div>`;
            }
            State.openModal('healthModal');
            return health;
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function restoreBackup(slot) {
        if (!window.confirm(`¿Restaurar el backup del slot ${String(slot).toUpperCase()}? Tus datos actuales serán reemplazados.`)) return;
        try {
            const result = await Api.post(`/system/restore/${String(slot).toUpperCase()}`, {});
            showToast(result.message || 'Backup restaurado.');
            await State.refreshAll();
            await Render.loadExceptions();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function runTests() {
        try {
            const result = await Api.post('/system/selftest', {});
            console.table(result.checks);
            const container = $id('selfTestResult');
            if (container) {
                container.innerHTML = result.checks.map((check) =>
                    `<div>${check.passed ? '✅' : '❌'} ${Render.esc(check.name)}${check.detail != null ? ` <span class="text-sm">(${Render.esc(JSON.stringify(check.detail))})</span>` : ''}</div>`
                ).join('');
            }
            showToast(`${result.passed}/${result.total} pruebas superadas.`, result.failed ? 'error' : 'success', 4000);
            return result;
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function bindEvents() {
        document.querySelectorAll('.nav-btn').forEach((button) => {
            button.addEventListener('click', () => activateModule(button.dataset.module));
        });

        const workspaceSelect = $id('workspaceSelect');
        if (workspaceSelect) {
            workspaceSelect.addEventListener('change', async () => {
                try {
                    await State.switchWorkspace(workspaceSelect.value);
                    if (AppState.activeModule === 'metrics') Analytics.refresh();
                    if (AppState.activeModule === 'backlog') Render.loadTimeline();
                } catch (error) {
                    showToast(error.message, 'error');
                }
            });
        }

        const themeToggle = $id('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', async () => {
                const current = document.documentElement.getAttribute('data-theme');
                const next = current === 'dark' ? 'light' : 'dark';
                State.applyTheme(next);
                try {
                    await Api.patch('/users/profile', { theme: next }, { silent: true });
                } catch (_) { /* el tema local sigue funcionando */ }
                if (AppState.activeModule === 'metrics') Analytics.refresh();
            });
        }

        const userMenuBtn = $id('userMenuBtn');
        const userDropdown = $id('userDropdown');
        if (userMenuBtn && userDropdown) {
            userMenuBtn.addEventListener('click', (event) => {
                event.stopPropagation();
                const open = userDropdown.classList.toggle('open');
                userMenuBtn.setAttribute('aria-expanded', String(open));
            });
            document.addEventListener('click', () => userDropdown.classList.remove('open'));
            userDropdown.addEventListener('click', (event) => event.stopPropagation());
            userDropdown.querySelectorAll('[data-action]').forEach((button) => {
                button.addEventListener('click', async () => {
                    const action = button.dataset.action;
                    userDropdown.classList.remove('open');
                    if (action === 'profile') {
                        activateModule('profile');
                        switchProfileTab('profile');
                    } else if (action === 'account') {
                        activateModule('profile');
                        switchProfileTab('account');
                    } else if (action === 'db-status') {
                        await showHealth();
                    } else if (action === 'logout') {
                        try {
                            await Api.post('/auth/logout', {});
                        } catch (_) { /* ignore */ }
                        window.location.href = '/login';
                    }
                });
            });
        }

        // Formularios de creación
        $id('habitForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const input = $id('habitInput');
            if (!input.value.trim()) return;
            await createNode({ module_type: 'habits', title: input.value.trim(), workspace_id: AppState.currentWorkspaceId });
            input.value = '';
        });
        $id('routineForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const input = $id('routineInput');
            if (!input.value.trim()) return;
            await createNode({
                module_type: 'routines',
                title: input.value.trim(),
                workspace_id: AppState.currentWorkspaceId,
                routine_category: $id('routineCategory').value,
            });
            input.value = '';
        });
        $id('backlogForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const input = $id('backlogInput');
            if (!input.value.trim()) return;
            await createNode({
                module_type: 'backlog',
                title: input.value.trim(),
                workspace_id: AppState.currentWorkspaceId,
                priority: $id('backlogPriority').value || null,
                tag: $id('backlogTag').value || null,
            });
            input.value = '';
        });

        // Filtros de backlog
        ['filterTag', 'filterPriority', 'sortBacklog'].forEach((id) => {
            $id(id)?.addEventListener('change', Render.renderBacklog);
        });

        // Subtarea
        $id('subtaskForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const title = $id('subtaskTitle').value.trim();
            const parentId = $id('subtaskParentId').value;
            const moduleType = $id('subtaskModule').value;
            if (!title || !parentId) return;
            await createNode({ module_type: moduleType, title, parent_id: parentId });
            State.closeModal('subtaskModal');
            $id('subtaskForm').reset();
        });

        // Agendar
        $id('assignForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const nodeId = $id('assignNodeSelect').value;
            const hour = $id('assignHour').value;
            if (!nodeId || !hour) return;
            try {
                await Api.post('/schedule/assign', {
                    node_id: nodeId,
                    hour_slot: hour,
                    recurring: $id('assignRecurring').checked,
                });
                State.closeModal('assignModal');
                showToast('Tarea agendada.');
                await State.refreshAll();
                await Render.loadTimeline();
            } catch (error) {
                showToast(error.message, 'error');
            }
        });

        // Editar tarea
        $id('editNodeForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const nodeId = $id('editNodeId').value;
            const node = State.nodeById(nodeId);
            if (!node) return;
            const selectedDays = Array.from(document.querySelectorAll('#editDaysPicker .day-chip.selected'))
                .map((chip) => Number(chip.dataset.day));
            const payload = {
                title: $id('editNodeTitle').value.trim(),
                schedule_days: selectedDays,
                period_start: $id('editPeriodStart').value || null,
                period_end: $id('editPeriodEnd').value || null,
                objective_id: $id('editObjective').value || null,
            };
            if (node.module_type === 'routines') payload.routine_category = $id('editNodeCategory').value || null;
            if (node.module_type === 'backlog') {
                payload.priority = $id('editNodePriority').value || null;
                payload.tag = $id('editNodeTag').value || null;
            }
            try {
                await Api.patch(`/nodes/${nodeId}`, payload);
                State.closeModal('editNodeModal');
                showToast('Tarea actualizada.');
                await State.refreshAll();
            } catch (error) {
                showToast(error.message, 'error');
            }
        });

        // Días del editor
        $id('editDaysPicker')?.addEventListener('click', (event) => {
            const chip = event.target.closest('.day-chip');
            if (chip) chip.classList.toggle('selected');
        });

        // Excepción
        $id('exceptionForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const title = $id('exceptionTitle').value.trim();
            const start = $id('exceptionStart').value;
            const end = $id('exceptionEnd').value;
            if (!title || !start || !end) return;
            if (new Date(end) <= new Date(start)) {
                showToast('La fecha final debe ser posterior a la inicial.', 'error');
                return;
            }
            try {
                await Api.post('/exceptions', {
                    title,
                    impact: $id('exceptionImpact').value,
                    area: $id('exceptionArea').value || null,
                    note: $id('exceptionNote').value || '',
                    start_time: start,
                    end_time: end,
                    workspace_id: AppState.currentWorkspaceId,
                });
                $id('exceptionTitle').value = '';
                $id('exceptionNote').value = '';
                setDefaultExceptionTimes();
                showToast('Excepción registrada.');
                await State.refreshAll();
                await Render.loadExceptions();
            } catch (error) {
                showToast(error.message, 'error');
            }
        });

        // Objetivo
        $id('objectiveForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const title = $id('objectiveTitle').value.trim();
            if (!title) return;
            try {
                await Api.post('/objectives', {
                    title,
                    horizon: $id('objectiveHorizon').value,
                    start_date: $id('objectiveStart').value || null,
                    end_date: $id('objectiveEnd').value || null,
                    description: $id('objectiveDescription').value || null,
                    workspace_id: AppState.currentWorkspaceId,
                });
                $id('objectiveForm').reset();
                showToast('Objetivo creado.');
                await State.refreshAll();
            } catch (error) {
                showToast(error.message, 'error');
            }
        });

        // Timer
        $id('timerStartBtn')?.addEventListener('click', TimerUI.start);
        $id('timerPauseBtn')?.addEventListener('click', TimerUI.pause);
        $id('timerResetBtn')?.addEventListener('click', TimerUI.reset);
        $id('timerSkipBtn')?.addEventListener('click', TimerUI.skip);
        $id('timerLinkBtn')?.addEventListener('click', TimerUI.openLinkModal);
        $id('timerUnlinkBtn')?.addEventListener('click', TimerUI.unlink);
        $id('timerCompleteTaskBtn')?.addEventListener('click', TimerUI.completeTask);
        document.querySelectorAll('[data-timer-mode]').forEach((button) => {
            button.addEventListener('click', () => TimerUI.setMode(button.dataset.timerMode));
        });
        $id('timerLinkConfirmBtn')?.addEventListener('click', () => {
            const select = $id('timerLinkSelect');
            if (select && select.value) TimerUI.link(select.value);
        });
        $id('sessionDoneNextBtn')?.addEventListener('click', TimerUI.nextPhase);
        $id('sessionDoneStopBtn')?.addEventListener('click', () => State.closeModal('sessionDoneModal'));

        // Perfil
        $id('profileSaveBtn')?.addEventListener('click', saveProfile);
        $id('profileTheme')?.addEventListener('change', () => {
            State.applyTheme($id('profileTheme').value, false);
        });
        $id('changePasswordBtn')?.addEventListener('click', changePassword);
        $id('deleteAccountBtn')?.addEventListener('click', deleteAccount);
        $id('profileExportBtn')?.addEventListener('click', exportBackup);
        $id('profileBackupBtn')?.addEventListener('click', createServerBackup);
        $id('profileRestoreABtn')?.addEventListener('click', () => restoreBackup('A'));
        $id('profileRestoreBBtn')?.addEventListener('click', () => restoreBackup('B'));
        $id('profileSelfTestBtn')?.addEventListener('click', runTests);

        // Tabs de perfil
        document.querySelectorAll('.profile-tab').forEach((button) => {
            button.addEventListener('click', () => switchProfileTab(button.dataset.profileTab));
        });

        // Export / import / informe / reset
        $id('exportBtn')?.addEventListener('click', exportBackup);
        $id('importFile')?.addEventListener('change', importBackup);
        $id('reportBtn')?.addEventListener('click', () => Api.download('/analytics/report.txt', 'informe.txt').catch((error) => showToast(error.message, 'error')));
        $id('resetBtn')?.addEventListener('click', () => State.openModal('resetModal'));
        $id('resetConfirmBtn')?.addEventListener('click', resetData);

        // Espacios
        $id('manageWorkspacesBtn')?.addEventListener('click', openWorkspacesModal);
        $id('workspaceCreateForm')?.addEventListener('submit', createWorkspace);
        $id('workspaceManageList')?.addEventListener('click', handleWorkspaceAction);

        // Logros
        $id('achModule')?.addEventListener('change', () => { AppState.achievementsPage = 0; Render.loadAchievements(); });
        $id('achTimer')?.addEventListener('change', () => { AppState.achievementsPage = 0; Render.loadAchievements(); });
        $id('achSearch')?.addEventListener('input', () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => { AppState.achievementsPage = 0; Render.loadAchievements(); }, 350);
        });
        $id('achPrevBtn')?.addEventListener('click', () => {
            AppState.achievementsPage = Math.max(0, AppState.achievementsPage - 1);
            Render.loadAchievements();
        });
        $id('achNextBtn')?.addEventListener('click', () => {
            AppState.achievementsPage += 1;
            Render.loadAchievements();
        });
        $id('achExportBtn')?.addEventListener('click', () => {
            const params = new URLSearchParams();
            if ($id('achModule').value) params.set('module_type', $id('achModule').value);
            if ($id('achTimer').value) params.set('timer', $id('achTimer').value);
            if ($id('achSearch').value) params.set('search', $id('achSearch').value);
            Api.download(`/achievements/export.csv?${params.toString()}`, 'logros.csv').catch((error) => showToast(error.message, 'error'));
        });

        // Historial
        document.querySelectorAll('#historyPeriodTabs .history-period-tab').forEach((button) => {
            button.addEventListener('click', () => {
                AppState.historyPeriod = button.dataset.period;
                AppState.historyOffset = 0;
                document.querySelectorAll('#historyPeriodTabs .history-period-tab').forEach((item) => {
                    item.classList.toggle('active', item === button);
                });
                Render.loadHistory();
            });
        });
        $id('historyPrevBtn')?.addEventListener('click', () => {
            AppState.historyOffset = Math.max(0, AppState.historyOffset - 30);
            Render.loadHistory();
        });
        $id('historyNextBtn')?.addEventListener('click', () => {
            AppState.historyOffset += 30;
            Render.loadHistory();
        });
        $id('historyExportBtn')?.addEventListener('click', () => {
            Api.download(`/analytics/history/export.csv?period=${encodeURIComponent(AppState.historyPeriod)}`, 'historial.csv').catch((error) => showToast(error.message, 'error'));
        });
        $id('historyReportBtn')?.addEventListener('click', () => {
            Api.download('/analytics/report.txt', 'informe.txt').catch((error) => showToast(error.message, 'error'));
        });

        // Métricas
        document.querySelectorAll('#metricsPeriodBar .period-btn').forEach((button) => {
            button.addEventListener('click', () => Analytics.setPeriod(button.dataset.period));
        });

        // Vinculación objetivo
        $id('linkObjectiveConfirmBtn')?.addEventListener('click', linkObjective);

        // Delegación global
        document.addEventListener('click', handleDelegatedClick);
        document.addEventListener('change', handleDelegatedChange);

        // Modales
        document.querySelectorAll('[data-close-modal]').forEach((button) => {
            button.addEventListener('click', () => button.closest('.modal-overlay')?.classList.remove('active'));
        });
        document.querySelectorAll('.modal-overlay').forEach((overlay) => {
            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) overlay.classList.remove('active');
            });
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') State.closeAllModals();
        });

        // Atajos de consola
        window.appHealth = showHealth;
        window.restoreBackup = restoreBackup;
        window.runTests = runTests;
    }

    async function createNode(payload) {
        try {
            await Api.post('/nodes', payload);
            showToast('Tarea creada.');
            await State.refreshAll();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    function switchProfileTab(tab) {
        document.querySelectorAll('.profile-tab').forEach((button) => {
            button.classList.toggle('active', button.dataset.profileTab === tab);
        });
        $id('profileTabProfile')?.classList.toggle('hidden', tab !== 'profile');
        $id('profileTabAccount')?.classList.toggle('hidden', tab !== 'account');
    }

    async function saveProfile() {
        try {
            const result = await Api.patch('/users/profile', {
                email: $id('profileEmail').value,
                theme: $id('profileTheme').value,
                logical_cutoff_hour: Number($id('profileCutoff').value),
                current_workspace_id: AppState.currentWorkspaceId,
                pomodoro_work_min: Number($id('profileWork').value),
                pomodoro_break_min: Number($id('profileBreak').value),
            });
            AppState.user = result;
            State.applyTheme(result.theme, false);
            showToast('Perfil actualizado.');
            await State.refreshAll();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function changePassword() {
        const current = $id('currentPassword').value;
        const next = $id('newPassword').value;
        const repeat = $id('repeatPassword').value;
        if (!current || !next) {
            showToast('Completa todos los campos de contraseña.', 'error');
            return;
        }
        if (next !== repeat) {
            showToast('Las contraseñas nuevas no coinciden.', 'error');
            return;
        }
        try {
            const result = await Api.post('/users/change-password', {
                current_password: current,
                new_password: next,
            });
            $id('currentPassword').value = '';
            $id('newPassword').value = '';
            $id('repeatPassword').value = '';
            showToast(result.message || 'Contraseña actualizada.');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function deleteAccount() {
        if (!window.confirm('¿Eliminar tu cuenta y todos tus datos? Esta acción no se puede deshacer.')) return;
        if (!window.confirm('Última confirmación: se guardará un backup de emergencia y se borrará la cuenta.')) return;
        try {
            await Api.delete('/users/account');
            window.location.href = '/login';
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function exportBackup() {
        try {
            await Api.download('/backup/export', 'productividad_pro_backup.json');
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function importBackup(event) {
        const file = event.target.files && event.target.files[0];
        event.target.value = '';
        if (!file) return;
        if (!window.confirm(`¿Importar "${file.name}"? Tus datos actuales serán reemplazados.`)) return;
        try {
            const result = await Api.upload('/backup/import', file);
            const warnings = result.warnings && result.warnings.length ? ` Avisos: ${result.warnings.join(' ')}` : '';
            showToast(`Importación completada (esquema v${result.source_schema_version}).${warnings}`, 'success', 5000);
            await State.refreshAll();
            await Render.loadExceptions();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function createServerBackup() {
        try {
            const result = await Api.post('/system/backup', {});
            showToast(result.message || 'Backup guardado.');
            await refreshDbStatus();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function resetData() {
        const value = $id('resetConfirmInput').value.trim();
        if (value !== 'REINICIAR') {
            showToast('Escribe REINICIAR para confirmar.', 'error');
            return;
        }
        try {
            const result = await Api.post('/system/reset', {});
            $id('resetConfirmInput').value = '';
            State.closeModal('resetModal');
            showToast(result.message || 'Datos reiniciados.');
            await State.refreshAll();
            await Render.loadExceptions();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function openWorkspacesModal() {
        renderWorkspaceManager();
        State.openModal('workspacesModal');
    }

    function renderWorkspaceManager() {
        const container = $id('workspaceManageList');
        if (!container) return;
        container.innerHTML = AppState.workspaces.map((workspace) => `
            <div style="display:flex;align-items:center;gap:.5rem;padding:.45rem 0;border-bottom:1px dashed var(--border);">
                <span style="flex:1;">${Render.esc(workspace.name)} ${workspace.is_default ? '<span class="text-sm">(por defecto)</span>' : ''}</span>
                <button class="icon-btn" data-workspace-action="rename" data-workspace-id="${Render.esc(workspace.id)}" title="Renombrar">✏️</button>
                ${AppState.workspaces.length > 1 ? `<button class="icon-btn danger" data-workspace-action="delete" data-workspace-id="${Render.esc(workspace.id)}" title="Eliminar">🗑️</button>` : ''}
            </div>`).join('');
    }

    async function createWorkspace(event) {
        event.preventDefault();
        const input = $id('workspaceNameInput');
        if (!input.value.trim()) return;
        try {
            await Api.post('/workspaces', { name: input.value.trim() });
            input.value = '';
            showToast('Espacio creado.');
            await State.refreshAll();
            renderWorkspaceManager();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    async function handleWorkspaceAction(event) {
        const button = event.target.closest('[data-workspace-action]');
        if (!button) return;
        const id = button.dataset.workspaceId;
        const workspace = AppState.workspaces.find((item) => item.id === id);
        if (!workspace) return;
        if (button.dataset.workspaceAction === 'rename') {
            const name = window.prompt('Nuevo nombre del espacio:', workspace.name);
            if (!name || name.trim() === workspace.name) return;
            try {
                await Api.patch(`/workspaces/${id}`, { name: name.trim() });
                showToast('Espacio renombrado.');
                await State.refreshAll();
                renderWorkspaceManager();
            } catch (error) {
                showToast(error.message, 'error');
            }
        } else if (button.dataset.workspaceAction === 'delete') {
            if (!window.confirm(`¿Eliminar "${workspace.name}" y todos sus datos?`)) return;
            try {
                await Api.delete(`/workspaces/${id}`);
                showToast('Espacio eliminado.');
                await State.refreshAll();
                renderWorkspaceManager();
            } catch (error) {
                showToast(error.message, 'error');
            }
        }
    }

    async function handleDelegatedClick(event) {
        const actionElement = event.target.closest('[data-action]');
        if (!actionElement) return;
        const action = actionElement.dataset.action;
        const nodeId = actionElement.dataset.nodeId;

        if (action === 'add-subtask') {
            const node = State.nodeById(nodeId);
            if (!node) return;
            $id('subtaskParentId').value = node.id;
            $id('subtaskModule').value = node.module_type;
            $id('subtaskParentTitle').textContent = `Padre: ${node.title}`;
            $id('subtaskTitle').value = '';
            State.openModal('subtaskModal');
        } else if (action === 'schedule-node') {
            openAssignModal(nodeId);
        } else if (action === 'assign-hour') {
            openAssignModal(null, actionElement.dataset.hour);
        } else if (action === 'edit-node') {
            openEditModal(nodeId);
        } else if (action === 'archive-node') {
            if (!window.confirm('¿Archivar esta tarea completada como logro definitivo?')) return;
            try {
                const result = await Api.post(`/nodes/${nodeId}/archive`, {});
                showToast(result.message || 'Logro guardado.');
                await State.refreshAll();
            } catch (error) {
                showToast(error.message, 'error');
            }
        } else if (action === 'delete-node') {
            if (!window.confirm('¿Eliminar esta tarea y todas sus subtareas?')) return;
            try {
                const result = await Api.delete(`/nodes/${nodeId}`);
                showToast(result.message || 'Tarea eliminada.');
                await State.refreshAll();
            } catch (error) {
                showToast(error.message, 'error');
            }
        } else if (action === 'link-timer-node') {
            await TimerUI.link(nodeId);
            await State.refreshAll();
        } else if (action === 'unassign-slot') {
            try {
                await Api.delete(`/schedule/${actionElement.dataset.slotId}`);
                showToast('Tarea quitada de la agenda.');
                await Render.loadTimeline();
            } catch (error) {
                showToast(error.message, 'error');
            }
        } else if (action === 'delete-exception') {
            if (!window.confirm('¿Eliminar esta excepción? Se recalculará el score.')) return;
            try {
                const result = await Api.delete(`/exceptions/${actionElement.dataset.exceptionId}`);
                showToast(result.message || 'Excepción eliminada.');
                await State.refreshAll();
                await Render.loadExceptions();
            } catch (error) {
                showToast(error.message, 'error');
            }
        } else if (action === 'link-node-objective') {
            openLinkObjectiveModal(nodeId, null);
        } else if (action === 'objective-link') {
            openLinkObjectiveModal(null, actionElement.dataset.objectiveId);
        } else if (action === 'unlink-objective') {
            try {
                await Api.delete(`/objectives/${actionElement.dataset.objectiveId}/link/${actionElement.dataset.nodeId}`);
                showToast('Tarea desvinculada del objetivo.');
                await State.refreshAll();
            } catch (error) {
                showToast(error.message, 'error');
            }
        } else if (action === 'delete-objective') {
            if (!window.confirm('¿Eliminar este objetivo? Las tareas no se eliminan.')) return;
            try {
                const result = await Api.delete(`/objectives/${actionElement.dataset.objectiveId}`);
                showToast(result.message || 'Objetivo eliminado.');
                await State.refreshAll();
            } catch (error) {
                showToast(error.message, 'error');
            }
        } else if (action === 'toggle-achievements') {
            actionElement.nextElementSibling?.classList.toggle('open');
        } else if (action === 'toggle-history') {
            actionElement.closest('.history-card')?.classList.toggle('open');
        }
    }

    async function handleDelegatedChange(event) {
        const checkbox = event.target.closest('[data-toggle-node]');
        if (!checkbox) return;
        const nodeId = checkbox.dataset.toggleNode;
        const completed = checkbox.checked;
        try {
            await Api.post(`/nodes/${nodeId}/toggle`, { completed });
            await State.refreshAll();
        } catch (error) {
            checkbox.checked = !completed;
            showToast(error.message, 'error');
        }
    }

    function openAssignModal(nodeId, hour) {
        const all = State.allNodes().filter((node) => !node.completed && !node.is_archived);
        const select = $id('assignNodeSelect');
        if (!select) return;
        if (!all.length) {
            showToast('No hay tareas pendientes para agendar.', 'info');
            return;
        }
        select.innerHTML = all.map((node) =>
            `<option value="${Render.esc(node.id)}">${Render.esc(node.title)} · ${Render.MODULE_LABELS[node.module_type] || node.module_type}</option>`
        ).join('');
        if (nodeId) select.value = nodeId;
        const node = State.nodeById(select.value);
        $id('assignNodeId').value = select.value;
        $id('assignTaskTitle').textContent = node ? `Tarea: ${node.title}` : '';
        const hourSelect = $id('assignHour');
        const hours = [];
        for (let index = 0; index < 28; index += 1) {
            const real = (4 + index) % 24;
            hours.push(`${String(real).padStart(2, '0')}:00`);
        }
        hourSelect.innerHTML = hours.map((value) => `<option value="${value}">${value}</option>`).join('');
        if (hour) hourSelect.value = hour;
        else {
            const nowHour = `${String(new Date().getHours()).padStart(2, '0')}:00`;
            if (hours.includes(nowHour)) hourSelect.value = nowHour;
        }
        State.openModal('assignModal');
    }

    function openEditModal(nodeId) {
        const node = State.nodeById(nodeId);
        if (!node) return;
        $id('editNodeId').value = node.id;
        $id('editNodeTitle').value = node.title;
        $id('editRoutineFields').classList.toggle('hidden', node.module_type !== 'routines');
        $id('editBacklogFields').classList.toggle('hidden', node.module_type !== 'backlog');
        if (node.module_type === 'routines') $id('editNodeCategory').value = node.routine_category || '';
        if (node.module_type === 'backlog') {
            $id('editNodePriority').value = node.priority || '';
            $id('editNodeTag').value = node.tag || '';
        }
        const selected = new Set(node.schedule_days || []);
        document.querySelectorAll('#editDaysPicker .day-chip').forEach((chip) => {
            chip.classList.toggle('selected', selected.has(Number(chip.dataset.day)));
        });
        $id('editPeriodStart').value = node.period_start || '';
        $id('editPeriodEnd').value = node.period_end || '';
        Render.populateObjectiveSelects();
        $id('editObjective').value = node.objective_id || '';
        State.openModal('editNodeModal');
    }

    function openLinkObjectiveModal(nodeId, objectiveId) {
        if (!AppState.objectives.length) {
            showToast('Crea un objetivo primero.', 'info');
            return;
        }
        Render.populateObjectiveSelects();
        const taskSelect = $id('linkObjectiveTaskSelect');
        const objectiveSelect = $id('linkObjectiveSelect');
        if (!taskSelect || !objectiveSelect) return;
        if (nodeId) taskSelect.value = nodeId;
        if (objectiveId) objectiveSelect.value = objectiveId;
        const node = State.nodeById(taskSelect.value);
        $id('linkObjectiveTaskTitle').textContent = node ? `Tarea: ${node.title}` : '';
        State.openModal('linkObjectiveModal');
    }

    async function linkObjective() {
        const objectiveId = $id('linkObjectiveSelect').value;
        const nodeId = $id('linkObjectiveTaskSelect').value;
        if (!objectiveId || !nodeId) {
            showToast('Selecciona una tarea y un objetivo.', 'error');
            return;
        }
        try {
            await Api.post(`/objectives/${objectiveId}/link`, { node_id: nodeId });
            State.closeModal('linkObjectiveModal');
            showToast('Tarea vinculada al objetivo.');
            await State.refreshAll();
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
