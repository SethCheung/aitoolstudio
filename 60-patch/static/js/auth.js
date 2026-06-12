(function (window) {
    if (window.StudioAuth) return;

    var AUTH_ME_URL = '/api/auth/me';
    var AUTH_LOGOUT_URL = '/api/auth/logout';
    var AUTH_CHANGE_PASSWORD_URL = '/api/auth/change-password';
    var fetchWrapped = false;

    function currentPathWithQuery() {
        var path = window.location.pathname || '/';
        var query = window.location.search || '';
        return path + query;
    }

    function loginRedirectUrl() {
        return '/login?next=' + encodeURIComponent(currentPathWithQuery());
    }

    function redirectToLogin() {
        if (window.location.pathname === '/login') return;
        window.location.href = loginRedirectUrl();
    }

    async function fetchMe() {
        try {
            var res = await fetch(AUTH_ME_URL, { credentials: 'include' });
            if (!res.ok) return null;
            var data = await res.json();
            return data && data.user ? data.user : null;
        } catch (e) {
            return null;
        }
    }

    async function guard(options) {
        var opts = Object.assign({ requireAuth: true, admin: false, redirect: true }, options || {});
        var user = await fetchMe();
        if (!user) {
            if (opts.requireAuth && opts.redirect) redirectToLogin();
            return { ok: false, user: null };
        }
        if (opts.admin && !user.is_admin) {
            if (opts.redirect) window.location.href = '/';
            return { ok: false, user: user };
        }
        return { ok: true, user: user };
    }

    async function logout() {
        try {
            await fetch(AUTH_LOGOUT_URL, { method: 'POST', credentials: 'include' });
        } catch (e) { }
        redirectToLogin();
    }

    async function changePassword(oldPassword, newPassword) {
        var res = await fetch(AUTH_CHANGE_PASSWORD_URL, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_password: String(oldPassword || ''),
                new_password: String(newPassword || ''),
            }),
        });
        if (!res.ok) {
            var message = '修改密码失败';
            try {
                var payload = await res.json();
                if (payload && payload.detail) message = String(payload.detail);
            } catch (e) { }
            throw new Error(message);
        }
        redirectToLogin();
        return true;
    }

    function installFetch401Handler() {
        if (fetchWrapped) return;
        fetchWrapped = true;
        var rawFetch = window.fetch.bind(window);
        window.fetch = async function () {
            var res = await rawFetch.apply(window, arguments);
            if (res && res.status === 401 && window.location.pathname !== '/login') {
                redirectToLogin();
            }
            return res;
        };
    }

    window.StudioAuth = {
        fetchMe: fetchMe,
        guard: guard,
        logout: logout,
        changePassword: changePassword,
        redirectToLogin: redirectToLogin,
        installFetch401Handler: installFetch401Handler,
    };

    if (window.location.pathname !== '/login') {
        installFetch401Handler();
    }
})(window);
