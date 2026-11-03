/* Pantalla de acceso y registro. */
(function () {
    'use strict';

    function $id(id) { return document.getElementById(id); }

    function setError(elementId, message) {
        const element = $id(elementId);
        if (element) element.textContent = message || '';
    }

    function setLoading(button, loading, label) {
        if (!button) return;
        button.disabled = loading;
        button.textContent = loading ? 'Procesando…' : label;
    }

    async function post(path, payload) {
        const response = await fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload),
        });
        const contentType = response.headers.get('content-type') || '';
        const data = contentType.includes('application/json') ? await response.json() : null;
        if (!response.ok) {
            let detail = data && data.detail ? data.detail : 'No se pudo completar la operación.';
            if (Array.isArray(detail)) {
                detail = detail.map((item) => item.msg || JSON.stringify(item)).join('\n');
            }
            throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        }
        return data;
    }

    function switchTab(tab) {
        document.querySelectorAll('.auth-tab').forEach((button) => {
            button.classList.toggle('active', button.dataset.authTab === tab);
        });
        $id('loginForm')?.classList.toggle('hidden', tab !== 'login');
        $id('registerForm')?.classList.toggle('hidden', tab !== 'register');
        setError('loginError', '');
        setError('registerError', '');
    }

    document.querySelectorAll('.auth-tab').forEach((button) => {
        button.addEventListener('click', () => switchTab(button.dataset.authTab));
    });

    $id('loginForm')?.addEventListener('submit', async (event) => {
        event.preventDefault();
        setError('loginError', '');
        const button = $id('loginSubmitBtn');
        setLoading(button, true, 'Entrar');
        try {
            await post('/api/v1/auth/login', {
                identifier: $id('loginIdentifier').value.trim(),
                password: $id('loginPassword').value,
            });
            window.location.href = '/';
        } catch (error) {
            setError('loginError', error.message);
            setLoading(button, false, 'Entrar');
        }
    });

    $id('registerForm')?.addEventListener('submit', async (event) => {
        event.preventDefault();
        setError('registerError', '');
        const password = $id('registerPassword').value;
        const repeat = $id('registerRepeat').value;
        if (password !== repeat) {
            setError('registerError', 'Las contraseñas no coinciden.');
            return;
        }
        const button = $id('registerSubmitBtn');
        setLoading(button, true, 'Crear cuenta');
        try {
            await post('/api/v1/auth/register', {
                username: $id('registerUsername').value.trim(),
                email: $id('registerEmail').value.trim(),
                password,
            });
            window.location.href = '/';
        } catch (error) {
            setError('registerError', error.message);
            setLoading(button, false, 'Crear cuenta');
        }
    });
})();
