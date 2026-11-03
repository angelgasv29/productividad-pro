/* Estado global de la aplicación y carga de datos. */
(function () {
    'use strict';

    const AppState = {
        user: null,
        workspaces: [],
        currentWorkspaceId: null,
        logicalDate: '',
        nodes: { habits: [], routines: [], backlog: [] },
        schedule: [],
        exceptions: [],
        objectives: [],
        achievements: [],
        achievementTotal: 0,
        scoreHistory: {},
        scoresByWorkspace: {},
        todayScore: null,
        globalStats: null,
        yearCountdown: null,
        activeModule: 'habits',
        timer: null,
        timeline: null,
        history: null,
        historyPeriod: 'week',
        historyOffset: 0,
        achievementsPage: 0,
        achievementsLimit: 25,
        charts: {},
        initialized: false,
    };

    function flatten(nodes, result = []) {
        (nodes || []).forEach((node) => {
            result.push(node);
            if (node.children && node.children.length) flatten(node.children, result);
        });
        return result;
    }

    function allNodes() {
        return flatten(AppState.nodes.habits)
            .concat(flatten(AppState.nodes.routines))
            .concat(flatten(AppState.nodes.backlog));
    }

    function nodeById(id) {
        return allNodes().find((node) => node.id === id) || null;
    }

    function pendingLeaves() {
        const all = allNodes();
        const parentIds = new Set(all.filter((node) => node.parent_id).map((node) => node.parent_id));
        return all.filter((node) => !node.completed && !node.is_archived && !parentIds.has(node.id));
    }

    function linkableTasks() {
        return allNodes().filter((node) => !node.is_archived);
    }

    function workspaceName(id) {
        const found = AppState.workspaces.find((workspace) => workspace.id === id);
        return found ? found.name : '';
    }

    function currentWorkspace() {
        return AppState.workspaces.find((workspace) => workspace.id === AppState.currentWorkspaceId) || null;
    }

    async function loadBootstrap(options = {}) {
        const data = await Api.get('/analytics/bootstrap', { silent: true });
        AppState.user = data.user;
        AppState.workspaces = data.workspaces || [];
        AppState.currentWorkspaceId = data.current_workspace_id;
        AppState.logicalDate = data.logical_date;
        AppState.nodes = data.nodes || { habits: [], routines: [], backlog: [] };
        AppState.schedule = data.schedule || [];
        AppState.exceptions = data.exceptions || [];
        AppState.objectives = data.objectives || [];
        AppState.achievements = data.achievements || [];
        AppState.achievementTotal = data.achievement_total || 0;
        AppState.scoreHistory = data.score_history || {};
        AppState.scoresByWorkspace = data.scores_by_workspace || {};
        AppState.todayScore = data.today_score;
        AppState.globalStats = data.global_stats;
        AppState.yearCountdown = data.year_countdown;
        AppState.initialized = true;
        if (AppState.user && AppState.user.theme) applyTheme(AppState.user.theme, false);
        return data;
    }

    function applyTheme(theme, persist = true) {
        document.documentElement.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light');
        const button = document.getElementById('themeToggle');
        if (button) button.textContent = theme === 'dark' ? '☀️' : '🌙';
        try { localStorage.setItem('prodpro-theme', theme); } catch (_) { /* ignore */ }
        if (persist && AppState.user) AppState.user.theme = theme;
    }

    function openModal(id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.add('active');
    }

    function closeModal(id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.remove('active');
    }

    function closeAllModals() {
        document.querySelectorAll('.modal-overlay.active').forEach((modal) => modal.classList.remove('active'));
    }

    async function switchWorkspace(workspaceId) {
        if (!workspaceId || workspaceId === AppState.currentWorkspaceId) return;
        await Api.post(`/workspaces/${workspaceId}/select`, {});
        await refreshAll();
        showToast('Espacio de trabajo cambiado.');
    }

    async function refreshAll() {
        await loadBootstrap();
        if (window.Render) Render.renderHeader();
        if (window.Render) Render.renderAll();
        if (window.TimerUI) {
            await TimerUI.refreshState();
            TimerUI.render();
        }
        if (AppState.activeModule === 'metrics' && window.Analytics) {
            await Analytics.refresh();
        }
        if (AppState.activeModule === 'backlog' && window.Render) {
            await Render.loadTimeline();
        }
        if (AppState.activeModule === 'history' && window.Render) {
            await Render.loadHistory();
        }
        if (AppState.activeModule === 'achievements' && window.Render) {
            await Render.loadAchievements();
        }
    }

    window.AppState = AppState;
    window.State = {
        flatten,
        allNodes,
        nodeById,
        pendingLeaves,
        linkableTasks,
        workspaceName,
        currentWorkspace,
        loadBootstrap,
        refreshAll,
        switchWorkspace,
        applyTheme,
        openModal,
        closeModal,
        closeAllModals,
    };
})();
