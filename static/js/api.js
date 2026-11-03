/* Cliente HTTP centralizado. Todas las llamadas usan la cookie HttpOnly. */
(function () {
    'use strict';

    const API_BASE = '/api/v1';
    let toastTimer = null;

    function showToast(message, type = 'success', duration = 2800) {
        const toast = document.getElementById('toast');
        const text = document.getElementById('toastText');
        const icon = document.getElementById('toastIcon');
        if (!toast || !text) return;
        text.textContent = message;
        if (icon) {
            icon.textContent = type === 'error' ? '⚠️' : type === 'info' ? 'ℹ️' : '✅';
        }
        toast.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.remove('show'), duration);
    }

    function normalizeDetail(detail, fallback) {
        if (!detail) return fallback;
        if (typeof detail === 'string') return detail;
        if (Array.isArray(detail)) {
            return detail
                .map((item) => {
                    if (typeof item === 'string') return item;
                    const location = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : '';
                    return `${location ? location + ': ' : ''}${item.msg || JSON.stringify(item)}`;
                })
                .join('\n');
        }
        if (typeof detail === 'object') {
            if (detail.message) return detail.message;
            return JSON.stringify(detail);
        }
        return String(detail);
    }

    async function request(path, options = {}) {
        const {
            method = 'GET',
            body = undefined,
            headers = {},
            loading = method !== 'GET',
            silent = false,
            raw = false,
        } = options;

        if (loading && !silent) showToast('Guardando…', 'info', 1200);

        const requestHeaders = { ...headers };
        let payload = body;
        if (body !== undefined && body !== null && !(body instanceof FormData)) {
            requestHeaders['Content-Type'] = 'application/json';
            payload = JSON.stringify(body);
        }

        let response;
        try {
            response = await fetch(API_BASE + path, {
                method,
                body: payload,
                headers: requestHeaders,
                credentials: 'same-origin',
                cache: 'no-store',
            });
        } catch (error) {
            if (!silent) showToast('No se pudo conectar con el servidor.', 'error', 4000);
            throw new Error('Error de red: ' + error.message);
        }

        if (response.status === 401) {
            window.location.href = '/login';
            throw new Error('Sesión expirada.');
        }

        if (raw) {
            if (!response.ok) {
                let detail = response.statusText;
                try {
                    const data = await response.json();
                    detail = data.detail || detail;
                } catch (_) { /* ignore */ }
                if (!silent) showToast(normalizeDetail(detail, 'La operación falló.'), 'error', 4500);
                throw new Error(normalizeDetail(detail, 'La operación falló.'));
            }
            return response;
        }

        const contentType = response.headers.get('content-type') || '';
        let data = null;
        if (contentType.includes('application/json')) {
            try {
                data = await response.json();
            } catch (_) {
                data = null;
            }
        } else {
            data = await response.text();
        }

        if (!response.ok) {
            const message = normalizeDetail(data && data.detail ? data.detail : data, 'La operación falló.');
            if (!silent) showToast(message, 'error', 4500);
            throw new Error(message);
        }

        return data;
    }

    async function download(path, fallbackName) {
        const response = await request(path, { raw: true, silent: true });
        const blob = await response.blob();
        let filename = fallbackName;
        const disposition = response.headers.get('content-disposition') || '';
        const match = disposition.match(/filename="?([^";]+)"?/i);
        if (match) filename = match[1];
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        showToast('Descarga iniciada.');
    }

    async function upload(path, file) {
        const data = new FormData();
        data.append('file', file);
        return request(path, { method: 'POST', body: data, loading: false });
    }

    window.Api = {
        request,
        get: (path, options = {}) => request(path, { ...options, method: 'GET' }),
        post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body }),
        patch: (path, body, options = {}) => request(path, { ...options, method: 'PATCH', body }),
        delete: (path, options = {}) => request(path, { ...options, method: 'DELETE' }),
        upload,
        download,
    };
    window.showToast = showToast;
    window.normalizeDetail = normalizeDetail;
})();
