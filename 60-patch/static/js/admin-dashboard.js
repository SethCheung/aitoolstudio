(function () {
    "use strict";

    var state = {
        appInfo: null,
        backups: []
    };

    function $(id) {
        return document.getElementById(id);
    }

    function text(id, value) {
        var el = $(id);
        if (el) el.textContent = value;
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
            btn.innerHTML = '<i id="themeToggleIcon" data-lucide="' + iconName + '"></i>';
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

    async function fetchJson(url, options) {
        var res = await fetch(url, Object.assign({ credentials: "include" }, options || {}));
        if (!res.ok) {
            throw new Error("HTTP " + res.status + " " + url);
        }
        return res.json();
    }

    function safeString(value, fallback) {
        if (value === null || value === undefined) return fallback;
        var str = String(value).trim();
        return str || fallback;
    }

    function normalizeVersion(raw) {
        if (!raw) return "";
        var s = String(raw).trim();
        return s.replace(/^v/i, "");
    }

    function compareVersion(a, b) {
        var pa = normalizeVersion(a).split(".").map(function (x) { return parseInt(x, 10) || 0; });
        var pb = normalizeVersion(b).split(".").map(function (x) { return parseInt(x, 10) || 0; });
        var len = Math.max(pa.length, pb.length);
        for (var i = 0; i < len; i += 1) {
            var x = pa[i] || 0;
            var y = pb[i] || 0;
            if (x > y) return 1;
            if (x < y) return -1;
        }
        return 0;
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
            redirect: false
        });
        if (!session || !session.user) {
            window.StudioAuth.redirectToLogin();
            return null;
        }

        var user = session.user;
        if (!user.is_admin) {
            if (authBadge) authBadge.textContent = "403 无后台权限";
            window.location.href = "/projects";
            return null;
        }

        if (authBadge) authBadge.textContent = "管理员已登录";
        return user;
    }

    async function loadAppInfo() {
        var info = await fetchJson("/api/app-info");
        state.appInfo = info || {};
        text("currentVersion", safeString(state.appInfo.version, "-"));

        var repoUrl = state.appInfo.repo_url;
        var repoLink = $("repoLink");
        if (repoLink) {
            if (repoUrl) {
                repoLink.href = repoUrl;
                repoLink.classList.remove("disabled");
            } else {
                repoLink.href = "#";
                repoLink.classList.add("disabled");
            }
        }
        return state.appInfo;
    }

    async function loadRemoteVersion() {
        var appInfo = state.appInfo || {};
        var versionUrl = appInfo.version_url;
        if (!versionUrl) {
            text("remoteVersion", "-");
            text("updateStatus", "缺少 version_url");
            return;
        }

        var remoteText = "";
        try {
            var res = await fetch(versionUrl, { cache: "no-store" });
            if (!res.ok) throw new Error("HTTP " + res.status);
            remoteText = (await res.text()).trim();
        } catch (e) {
            text("remoteVersion", "读取失败");
            text("updateStatus", "无法访问远程版本");
            return;
        }

        var remoteVersion = "";
        try {
            if (remoteText.startsWith("{")) {
                var payload = JSON.parse(remoteText);
                remoteVersion = payload.version || payload.tag || payload.latest || "";
            } else {
                remoteVersion = remoteText.split(/\s+/)[0];
            }
        } catch (e2) {
            remoteVersion = remoteText.split(/\s+/)[0];
        }

        remoteVersion = safeString(remoteVersion, "-");
        text("remoteVersion", remoteVersion);

        var current = safeString(appInfo.version, "");
        if (!current || remoteVersion === "-") {
            text("updateStatus", "版本信息不完整");
            return;
        }

        var cmp = compareVersion(current, remoteVersion);
        if (cmp < 0) text("updateStatus", "可更新");
        else if (cmp === 0) text("updateStatus", "已是最新");
        else text("updateStatus", "本地高于远程");
    }

    function setBusy(id, busy) {
        var el = $(id);
        if (!el) return;
        el.disabled = !!busy;
    }

    async function pollRecoverAndReload(messageTargetId) {
        var start = Date.now();
        var timeoutMs = 120000;
        var intervalMs = 3000;
        text(messageTargetId, "已提交，等待服务重启恢复...");

        while (Date.now() - start < timeoutMs) {
            await new Promise(function (resolve) { setTimeout(resolve, intervalMs); });
            try {
                await fetchJson("/api/app-info");
                text(messageTargetId, "服务已恢复，正在刷新页面...");
                window.location.reload();
                return;
            } catch (e) {}
        }
        text(messageTargetId, "恢复超时，请手动刷新检查状态。");
    }

    async function runUpdate() {
        setBusy("runUpdateBtn", true);
        try {
            text("updateMessage", "开始执行更新...");
            await fetchJson("/api/update-from-github", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ auto_restart: true, restart_delay: 3 })
            });
            await pollRecoverAndReload("updateMessage");
        } catch (e) {
            text("updateMessage", "更新失败: " + e.message);
        } finally {
            setBusy("runUpdateBtn", false);
        }
    }

    function parseBackupId(item) {
        if (!item) return "";
        if (typeof item === "string") return item;
        return item.backup_id || item.id || item.name || "";
    }

    function parseBackupLabel(item, idx) {
        if (typeof item === "string") return item;
        if (!item || typeof item !== "object") return "备份 " + (idx + 1);
        if (item.created_at) {
            var date = new Date(Number(item.created_at) * 1000);
            var labelTime = Number.isNaN(date.getTime())
                ? String(item.created_at)
                : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
            return labelTime + " / " + parseBackupId(item);
        }
        return parseBackupId(item);
    }

    async function loadBackups() {
        var select = $("backupSelect");
        var rollbackBtn = $("rollbackBtn");
        if (!select) return;

        select.innerHTML = "";
        select.disabled = true;
        if (rollbackBtn) rollbackBtn.disabled = true;
        text("backupMessage", "正在读取备份...");

        try {
            var data = await fetchJson("/api/update-backups");
            var list = Array.isArray(data) ? data : (Array.isArray(data.backups) ? data.backups : []);
            state.backups = list;

            if (!list.length) {
                var empty = document.createElement("option");
                empty.value = "";
                empty.textContent = "暂无备份";
                select.appendChild(empty);
                text("backupMessage", "没有可用备份。");
                return;
            }

            list.forEach(function (item, idx) {
                var id = parseBackupId(item);
                if (!id) return;
                var option = document.createElement("option");
                option.value = id;
                option.textContent = parseBackupLabel(item, idx);
                select.appendChild(option);
            });

            if (!select.options.length) {
                var inv = document.createElement("option");
                inv.value = "";
                inv.textContent = "备份数据不可用";
                select.appendChild(inv);
                text("backupMessage", "返回数据缺少备份名称。");
                return;
            }

            select.disabled = false;
            if (rollbackBtn) rollbackBtn.disabled = false;
            text("backupMessage", "已载入 " + select.options.length + " 条备份。");
        } catch (e) {
            var fail = document.createElement("option");
            fail.value = "";
            fail.textContent = "读取失败";
            select.appendChild(fail);
            text("backupMessage", "备份读取失败: " + e.message);
        }
    }

    async function runRollback() {
        var select = $("backupSelect");
        if (!select || !select.value) {
            text("backupMessage", "请先选择备份。");
            return;
        }

        setBusy("rollbackBtn", true);
        try {
            text("backupMessage", "开始回滚到备份: " + select.value);
            await fetchJson("/api/update-rollback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: select.value,
                    auto_restart: true,
                    restart_delay: 3
                })
            });
            await pollRecoverAndReload("backupMessage");
        } catch (e) {
            text("backupMessage", "回滚失败: " + e.message);
        } finally {
            setBusy("rollbackBtn", false);
        }
    }

    async function bootstrap() {
        var user = await guardAdmin();
        if (!user) return;

        bindThemeToggle();
        await loadAppInfo();
        await Promise.all([loadRemoteVersion(), loadBackups()]);

        var checkBtn = $("checkUpdateBtn");
        var updateBtn = $("runUpdateBtn");
        var refreshBackupsBtn = $("refreshBackupsBtn");
        var rollbackBtn = $("rollbackBtn");

        if (checkBtn) checkBtn.addEventListener("click", loadRemoteVersion);
        if (updateBtn) updateBtn.addEventListener("click", runUpdate);
        if (refreshBackupsBtn) refreshBackupsBtn.addEventListener("click", loadBackups);
        if (rollbackBtn) rollbackBtn.addEventListener("click", runRollback);

        if (window.lucide && typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootstrap);
    } else {
        bootstrap();
    }
})();
