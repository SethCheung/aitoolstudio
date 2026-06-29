(function () {
    "use strict";

    var state = {
        currentUser: null,
        users: [],
    };

    function $(id) {
        return document.getElementById(id);
    }

    function esc(text) {
        return String(text || "").replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[ch];
        });
    }

    function toDateText(isoText) {
        var text = String(isoText || "").trim();
        if (!text) return "-";
        var d = new Date(text);
        if (Number.isNaN(d.getTime())) return text;
        return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    }

    function setSummary() {
        var summaryEl = $("headSummary");
        if (!summaryEl) return;
        var total = state.users.length;
        var active = state.users.filter(function (x) { return !x.is_disabled; }).length;
        summaryEl.textContent = "共 " + total + " 人，启用 " + active + " 人";
    }

    function setMessage(id, text) {
        var el = $(id);
        if (el) el.textContent = text || "";
    }

    async function fetchJson(url, options) {
        var res = await fetch(url, Object.assign({ credentials: "include" }, options || {}));
        if (!res.ok) {
            var detail = "请求失败";
            try {
                var body = await res.json();
                if (body && body.detail) detail = String(body.detail);
            } catch (_e) {}
            throw new Error(detail);
        }
        return await res.json();
    }

    function getCurrentTheme() {
        if (window.StudioTheme && typeof window.StudioTheme.get === "function") {
            return window.StudioTheme.get() === "dark" ? "dark" : "light";
        }
        var saved = localStorage.getItem("studio_theme") || localStorage.getItem("canvas_theme") || "light";
        return saved === "dark" ? "dark" : "light";
    }

    function syncThemeButton(theme) {
        var btn = $("themeToggleBtn");
        if (!btn) return;
        var isDark = theme === "dark";
        var iconName = isDark ? "sun-medium" : "moon-star";
        btn.classList.toggle("active", isDark);
        btn.setAttribute("aria-label", isDark ? "切换到浅色主题" : "切换到深色主题");
        btn.title = isDark ? "切换到浅色主题" : "切换到深色主题";
        var icon = btn.querySelector("[data-lucide]");
        if (!icon || icon.getAttribute("data-lucide") !== iconName) {
            btn.innerHTML = '<i data-lucide="' + iconName + '"></i>';
        }
        if (window.lucide && typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons();
        }
    }

    function bindThemeToggle() {
        var btn = $("themeToggleBtn");
        if (!btn) return;
        syncThemeButton(getCurrentTheme());
        btn.addEventListener("click", function () {
            var next = getCurrentTheme() === "dark" ? "light" : "dark";
            if (window.StudioTheme && typeof window.StudioTheme.set === "function") {
                window.StudioTheme.set(next);
            } else {
                localStorage.setItem("studio_theme", next);
                localStorage.setItem("canvas_theme", next);
                document.documentElement.classList.toggle("theme-dark", next === "dark");
            }
            syncThemeButton(next);
        });
        window.addEventListener("studio-theme-change", function (event) {
            var nextTheme = event && event.detail ? event.detail.theme : getCurrentTheme();
            syncThemeButton(nextTheme === "dark" ? "dark" : "light");
        });
        window.addEventListener("storage", function (event) {
            if (event.key === "studio_theme" || event.key === "canvas_theme") {
                syncThemeButton(getCurrentTheme());
            }
        });
    }

    async function guardAdmin() {
        var authBadge = $("authBadge");
        if (!window.StudioAuth) {
            if (authBadge) authBadge.textContent = "缺少认证模块";
            window.location.href = "/projects";
            return null;
        }
        var session = await window.StudioAuth.guard({
            requireAuth: true,
            requireAdmin: true,
            admin: true,
            redirect: false,
        });
        if (!session || !session.user) {
            window.StudioAuth.redirectToLogin();
            return null;
        }
        if (!session.user.is_admin) {
            if (authBadge) authBadge.textContent = "403 无后台权限";
            window.location.href = "/projects";
            return null;
        }
        state.currentUser = session.user;
        if (authBadge) authBadge.textContent = "管理员已登录: " + session.user.username;
        return session.user;
    }

    function actionButton(label, iconName, className, onClick) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = className || "";
        btn.innerHTML = '<i data-lucide="' + esc(iconName) + '"></i><span>' + esc(label) + "</span>";
        btn.addEventListener("click", onClick);
        return btn;
    }

    function renderUsers() {
        var listEl = $("usersList");
        var tpl = $("userRowTpl");
        if (!listEl || !tpl) return;
        listEl.innerHTML = "";
        if (!state.users.length) {
            setMessage("listMessage", "暂无用户");
            return;
        }
        setMessage("listMessage", "");
        state.users.forEach(function (user) {
            var row = tpl.content.firstElementChild.cloneNode(true);
            var usernameEl = row.querySelector(".username");
            var selfTagEl = row.querySelector(".self-tag");
            var roleEl = row.querySelector(".role-badge");
            var statusEl = row.querySelector(".status-badge");
            var createdAtEl = row.querySelector(".created-at");
            var actionsEl = row.querySelector(".actions");

            usernameEl.textContent = user.username || "-";
            roleEl.textContent = user.is_admin ? "管理员" : "普通用户";
            statusEl.textContent = user.is_disabled ? "已禁用" : "启用中";
            statusEl.classList.toggle("ok", !user.is_disabled);
            statusEl.classList.toggle("bad", !!user.is_disabled);
            createdAtEl.textContent = toDateText(user.created_at);

            if (state.currentUser && Number(state.currentUser.id) === Number(user.id) && selfTagEl) {
                selfTagEl.classList.remove("hidden");
            }

            actionsEl.appendChild(actionButton(
                user.is_admin ? "设为普通" : "设为管理员",
                user.is_admin ? "shield-off" : "shield",
                "",
                function () { handleToggleAdmin(user); }
            ));
            actionsEl.appendChild(actionButton(
                user.is_disabled ? "启用" : "禁用",
                user.is_disabled ? "user-check" : "user-x",
                user.is_disabled ? "ghost-ok" : "ghost-danger",
                function () { handleToggleDisabled(user); }
            ));
            actionsEl.appendChild(actionButton(
                "重置密码",
                "key-round",
                "",
                function () { handleResetPassword(user); }
            ));

            listEl.appendChild(row);
        });
        if (window.lucide && typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons();
        }
    }

    async function reloadUsers(message) {
        var data = await fetchJson("/api/auth/users");
        state.users = Array.isArray(data.users) ? data.users : [];
        setSummary();
        renderUsers();
        if (message) setMessage("listMessage", message);
    }

    async function handleToggleAdmin(user) {
        var nextValue = !user.is_admin;
        var tip = nextValue ? "确认设为管理员？" : "确认取消管理员权限？";
        if (!window.confirm(tip)) return;
        try {
            await fetchJson("/api/auth/users/" + encodeURIComponent(user.id), {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_admin: nextValue }),
            });
            await reloadUsers("角色更新成功");
        } catch (err) {
            setMessage("listMessage", "角色更新失败: " + err.message);
        }
    }

    async function handleToggleDisabled(user) {
        var nextValue = !user.is_disabled;
        var tip = nextValue ? "确认禁用该用户？" : "确认启用该用户？";
        if (!window.confirm(tip)) return;
        try {
            await fetchJson("/api/auth/users/" + encodeURIComponent(user.id), {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_disabled: nextValue }),
            });
            await reloadUsers(nextValue ? "用户已禁用" : "用户已启用");
        } catch (err) {
            setMessage("listMessage", "状态更新失败: " + err.message);
        }
    }

    async function handleResetPassword(user) {
        var nextPassword = window.prompt("输入新密码（至少 6 位）", "");
        if (nextPassword === null) return;
        var text = String(nextPassword || "").trim();
        if (text.length < 6) {
            setMessage("listMessage", "重置失败: 密码至少 6 位");
            return;
        }
        try {
            await fetchJson("/api/auth/users/" + encodeURIComponent(user.id) + "/reset-password", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_password: text }),
            });
            await reloadUsers("密码已重置，旧会话已失效");
        } catch (err) {
            setMessage("listMessage", "重置密码失败: " + err.message);
        }
    }

    function bindCreateUser() {
        var form = $("createForm");
        var usernameInput = $("createUsername");
        var passwordInput = $("createPassword");
        var adminInput = $("createAdmin");
        if (!form || !usernameInput || !passwordInput || !adminInput) return;

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            var username = String(usernameInput.value || "").trim();
            var password = String(passwordInput.value || "");
            var isAdmin = !!adminInput.checked;
            if (!username || password.length < 6) {
                setMessage("createMessage", "请输入合法用户名和至少 6 位密码");
                return;
            }
            setMessage("createMessage", "创建中...");
            try {
                await fetchJson("/api/auth/users", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username: username,
                        password: password,
                        is_admin: isAdmin,
                    }),
                });
                usernameInput.value = "";
                passwordInput.value = "";
                adminInput.checked = false;
                setMessage("createMessage", "创建成功");
                await reloadUsers();
            } catch (err) {
                setMessage("createMessage", "创建失败: " + err.message);
            }
        });
    }

    async function bootstrap() {
        bindThemeToggle();
        bindCreateUser();
        var refreshBtn = $("refreshBtn");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", function () {
                reloadUsers("已刷新").catch(function (err) {
                    setMessage("listMessage", "刷新失败: " + err.message);
                });
            });
        }
        var user = await guardAdmin();
        if (!user) return;
        try {
            await reloadUsers();
        } catch (err) {
            setMessage("listMessage", "加载失败: " + err.message);
        }
    }

    bootstrap();
})();
