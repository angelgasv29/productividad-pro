/* Gráficos y paneles analíticos. */
(function () {
    'use strict';

    function cssVar(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    function destroyChart(key) {
        if (AppState.charts[key]) {
            AppState.charts[key].destroy();
            delete AppState.charts[key];
        }
    }

    function chartAvailable() {
        return typeof window.Chart !== 'undefined';
    }

    function setPeriod(period) {
        AppState.metricsPeriod = period;
        document.querySelectorAll('#metricsPeriodBar .period-btn').forEach((button) => {
            button.classList.toggle('active', button.dataset.period === period);
        });
        refresh();
    }

    async function refresh() {
        const period = AppState.metricsPeriod || 'week';
        const results = await Promise.allSettled([
            Api.get(`/analytics/history?period=${encodeURIComponent(period)}&limit=30`, { silent: true }),
            Api.get(`/analytics/categories?workspace_id=${encodeURIComponent(AppState.currentWorkspaceId)}`, { silent: true }),
            Api.get(`/analytics/objectives-history?workspace_id=${encodeURIComponent(AppState.currentWorkspaceId)}`, { silent: true }),
            Api.get(`/analytics/heatmap?weeks=16`, { silent: true }),
            Api.get(`/analytics/timer-impact?workspace_id=${encodeURIComponent(AppState.currentWorkspaceId)}`, { silent: true }),
            Api.get(`/analytics/correlation`, { silent: true }),
        ]);

        const [history, categories, objectives, heatmap, timerImpact, correlation] = results.map((result) =>
            result.status === 'fulfilled' ? result.value : null
        );

        if (history) AppState.metricsHistory = history;
        if (categories) AppState.categories = categories;
        if (objectives) AppState.objectiveHistory = objectives;
        if (heatmap) AppState.heatmap = heatmap;
        if (timerImpact) AppState.timerImpact = timerImpact;
        if (correlation) AppState.correlation = correlation;

        Render.renderHeatmap();
        Render.renderTimerImpact();
        Render.renderCorrelation();
        renderCharts();
    }

    function emptyChart(canvas, message) {
        if (!canvas) return;
        const parent = canvas.parentElement;
        if (parent) {
            parent.innerHTML = `<div class="text-sm" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">${message}</div>`;
        }
    }

    function renderCharts() {
        if (!chartAvailable()) {
            const message = 'Chart.js no está disponible. Coloca chart.umd.min.js en /static/vendor/.';
            emptyChart(document.getElementById('scoreChart'), message);
            emptyChart(document.getElementById('categoryChart'), message);
            emptyChart(document.getElementById('objectiveChart'), message);
            return;
        }

        Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
        Chart.defaults.color = cssVar('--text-muted');
        const gridColor = cssVar('--border');
        const primary = cssVar('--primary');
        const success = cssVar('--success');
        const warning = cssVar('--warning');

        const history = AppState.metricsHistory;
        const scoreCanvas = document.getElementById('scoreChart');
        if (scoreCanvas) {
            destroyChart('score');
            const buckets = history ? history.items.slice().reverse() : [];
            AppState.charts.score = new Chart(scoreCanvas, {
                type: 'line',
                data: {
                    labels: buckets.map((bucket) => bucket.title),
                    datasets: [{
                        label: 'Score promedio',
                        data: buckets.map((bucket) => bucket.score_avg),
                        borderColor: primary,
                        backgroundColor: primary + '22',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { min: 0, max: 100, grid: { color: gridColor }, ticks: { stepSize: 20 } },
                        x: { grid: { display: false } },
                    },
                },
            });
        }

        const categoryCanvas = document.getElementById('categoryChart');
        if (categoryCanvas) {
            destroyChart('category');
            const categories = AppState.categories ? AppState.categories.categories : [];
            const colors = ['#fb923c', '#38bdf8', '#f43f5e', '#a855f7', '#94a3b8', '#10b981'];
            AppState.charts.category = new Chart(categoryCanvas, {
                type: 'doughnut',
                data: {
                    labels: categories.map((item) => item.category),
                    datasets: [{
                        data: categories.map((item) => item.total),
                        backgroundColor: categories.map((item, index) => colors[index % colors.length]),
                        borderWidth: 1,
                        borderColor: cssVar('--bg-surface'),
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10 } },
                    },
                },
            });
        }

        const objectiveCanvas = document.getElementById('objectiveChart');
        if (objectiveCanvas) {
            destroyChart('objective');
            const data = AppState.objectiveHistory || { labels: [], datasets: [] };
            const palette = ['#4f46e5', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];
            AppState.charts.objective = new Chart(objectiveCanvas, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: data.datasets.map((dataset, index) => ({
                        label: dataset.label,
                        data: dataset.data,
                        borderColor: palette[index % palette.length],
                        backgroundColor: palette[index % palette.length] + '22',
                        spanGaps: dataset.span_gaps !== false,
                        tension: 0.25,
                        pointRadius: 3,
                    })),
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10 } } },
                    scales: {
                        y: { min: 0, max: 100, grid: { color: gridColor }, ticks: { callback: (value) => value + '%' } },
                        x: { grid: { display: false } },
                    },
                },
            });
        }
    }

    window.Analytics = { refresh, setPeriod, renderCharts };
})();
