(function () {
    "use strict";

    var state = {
        user: null,
        activeProjects: [],
        trashProjects: [],
        mode: "active",
        view: "grid",
        query: "",
        sort: "updated_desc",
        passwordSubmitting: false,
    };

    var els = {};

    function $(id) { return document.getElementById(id); }

    function esc(s) {
        return String(s || "").replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[ch];
        });
    }

    function toTimeText(value) {
        var n = Number(value || 0);
        if (!n) return "--";
        var ms = n < 10000000000 ? n * 1000 : n;
        var d = new Date(ms);
        if (Number.isNaN(d.getTime())) return "--";
        return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    }

    function projectItem(project) {
        var meta = project && project.default_canvas ? project.default_canvas : {};
        return {
            projectId: String(project && project.id ? project.id : ""),
            canvasId: String(meta.id || project.default_canvas_id || ""),
            title: String(project && project.title ? project.title : "未命名项目"),
            kind: String(meta.kind || project.kind || "classic").toLowerCase() === "smart" ? "smart" : "classic",
            updatedAt: Math.max(Number(project.updated_at || 0), Number(meta.updated_at || 0)),
            createdAt: Number(project.created_at || meta.created_at || 0),
            nodeCount: Number(project.node_count || meta.node_count || 0),
            owner: project.owner && project.owner.username ? String(project.owner.username) : "",
            archivedAt: Number(project.archived_at || 0),
        };
    }

    function setStatus(text) {
        els.statusBar.textContent = text;
    }

    function setPasswordMessage(text) {
        if (!els.passwordMessage) return;
        els.passwordMessage.textContent = text || "";
    }

    function closePasswordModal() {
        if (!els.passwordModal) return;
        els.passwordModal.classList.add("hidden");
        els.passwordModal.setAttribute("aria-hidden", "true");
        if (els.passwordForm) els.passwordForm.reset();
        setPasswordMessage("");
        state.passwordSubmitting = false;
        if (els.passwordSubmitBtn) els.passwordSubmitBtn.disabled = false;
    }

    function openPasswordModal() {
        if (!els.passwordModal) return;
        els.passwordModal.classList.remove("hidden");
        els.passwordModal.setAttribute("aria-hidden", "false");
        if (els.oldPasswordInput) els.oldPasswordInput.focus();
    }

    function setSummary() {
        if (!els.pageSummary) return;
        els.pageSummary.textContent = state.activeProjects.length + " 个项目 / " + state.trashProjects.length + " 个回收站";
    }

    function getThemeValue() {
        try {
            if (window.StudioTheme && typeof window.StudioTheme.get === "function") {
                var current = String(window.StudioTheme.get() || "").toLowerCase();
                if (current === "dark" || current === "light") return current;
            }
            var stored = String(localStorage.getItem("studio_theme") || localStorage.getItem("canvas_theme") || "").toLowerCase();
            if (stored === "dark" || stored === "light") return stored;
        } catch (_e) {}
        return "light";
    }

    function applyTheme(theme) {
        var next = theme === "dark" ? "dark" : "light";
        var isDark = next === "dark";
        document.documentElement.classList.toggle("theme-dark", isDark);
        document.documentElement.classList.toggle("studio-theme-dark", isDark);
        if (document.body) {
            document.body.classList.toggle("theme-dark", isDark);
            document.body.classList.toggle("studio-theme-dark", isDark);
        }
        if (els.themeToggleBtn) {
            els.themeToggleBtn.classList.toggle("active", isDark);
            els.themeToggleBtn.title = isDark ? "切换到浅色模式" : "切换到深色模式";
            els.themeToggleBtn.setAttribute("aria-label", isDark ? "切换到浅色模式" : "切换到深色模式");
            var iconName = isDark ? "sun" : "moon";
            var icon = els.themeToggleBtn.querySelector("[data-lucide]");
            if (!icon || icon.getAttribute("data-lucide") !== iconName) {
                els.themeToggleBtn.innerHTML = '<i data-lucide="' + iconName + '" class="icon-16"></i>';
            }
        }
        if (window.lucide) window.lucide.createIcons();
    }

    function setTheme(theme) {
        var next = theme === "dark" ? "dark" : "light";
        try {
            if (window.StudioTheme && typeof window.StudioTheme.set === "function") {
                window.StudioTheme.set(next);
            } else {
                localStorage.setItem("studio_theme", next);
                localStorage.setItem("canvas_theme", next);
            }
        } catch (_e) {}
        applyTheme(next);
    }

    async function requestJson(url, options) {
        var res = await fetch(url, Object.assign({ credentials: "include" }, options || {}));
        if (!res.ok) {
            var message = "请求失败";
            try {
                var data = await res.json();
                if (data && data.detail) message = String(data.detail);
            } catch (_e) {}
            throw new Error(message);
        }
        return await res.json();
    }

    async function loadProjects() {
        setStatus("加载中...");
        var results = await Promise.all([
            requestJson("/api/projects"),
            requestJson("/api/projects/trash"),
        ]);
        state.activeProjects = (results[0].projects || []).map(projectItem);
        state.trashProjects = (results[1].projects || []).map(projectItem);
        els.activeCount.textContent = String(state.activeProjects.length);
        els.trashCount.textContent = String(state.trashProjects.length);
        setSummary();
    }

    function visibleProjects() {
        var list = state.mode === "trash" ? state.trashProjects.slice() : state.activeProjects.slice();
        var q = state.query.trim().toLowerCase();
        if (q) {
            list = list.filter(function (item) {
                return item.title.toLowerCase().indexOf(q) >= 0 || item.owner.toLowerCase().indexOf(q) >= 0;
            });
        }
        if (state.sort === "name_asc") {
            list.sort(function (a, b) { return a.title.localeCompare(b.title, "zh-Hans-CN"); });
        } else if (state.sort === "created_asc") {
            list.sort(function (a, b) { return a.createdAt - b.createdAt; });
        } else {
            list.sort(function (a, b) { return b.updatedAt - a.updatedAt; });
        }
        return list;
    }

    function switchTab(mode) {
        state.mode = mode;
        els.activeTabBtn.classList.toggle("active", mode === "active");
        els.trashTabBtn.classList.toggle("active", mode === "trash");
        renderList();
    }

    function openProject(item) {
        if (!item.canvasId) return;
        var url = item.kind === "smart" ? "/smart-canvas?id=" : "/canvas?id=";
        window.location.href = url + encodeURIComponent(item.canvasId);
    }

    async function createProject(kind) {
        var raw = window.prompt(kind === "smart" ? "智能项目名称" : "项目名称", "");
        if (raw === null) return;
        var title = raw.trim() || (kind === "smart" ? "智能项目" : "新项目");
        setStatus("创建中...");
        try {
            var data = await requestJson("/api/projects", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: title, kind: kind }),
            });
            var canvasId = data && data.canvas && data.canvas.id ? String(data.canvas.id) : "";
            if (!canvasId) throw new Error("创建成功但画布 ID 缺失");
            var path = kind === "smart" ? "/smart-canvas?id=" : "/canvas?id=";
            window.location.href = path + encodeURIComponent(canvasId);
        } catch (err) {
            setStatus("创建失败: " + err.message);
        }
    }

    async function renameProject(item) {
        var next = window.prompt("重命名项目", item.title);
        if (next === null) return;
        var title = next.trim();
        if (!title || title === item.title) return;
        try {
            await requestJson("/api/projects/" + encodeURIComponent(item.projectId), {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: title }),
            });
            await reloadAndRender("已重命名");
        } catch (err) {
            setStatus("重命名失败: " + err.message);
        }
    }

    async function archiveProject(item) {
        if (!window.confirm("确认归档该项目？")) return;
        try {
            await requestJson("/api/projects/" + encodeURIComponent(item.projectId), { method: "DELETE" });
            await reloadAndRender("已归档");
        } catch (err) {
            setStatus("归档失败: " + err.message);
        }
    }

    async function restoreProject(item) {
        try {
            await requestJson("/api/projects/" + encodeURIComponent(item.projectId) + "/restore", { method: "POST" });
            await reloadAndRender("已恢复");
        } catch (err) {
            setStatus("恢复失败: " + err.message);
        }
    }

    async function purgeProject(item) {
        if (!window.confirm("彻底删除后无法恢复，继续？")) return;
        try {
            await requestJson("/api/projects/" + encodeURIComponent(item.projectId) + "/purge", { method: "DELETE" });
            await reloadAndRender("已删除");
        } catch (err) {
            setStatus("删除失败: " + err.message);
        }
    }

    function actionButton(text, icon, className, handler) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = className || "tool-btn";
        btn.innerHTML = '<i data-lucide="' + esc(icon) + '" class="icon-14"></i><span>' + esc(text) + "</span>";
        btn.onclick = handler;
        return btn;
    }

    function renderList() {
        var items = visibleProjects();
        els.projectList.className = "project-list " + state.view;
        els.projectList.innerHTML = "";
        if (!items.length) {
            setStatus(state.mode === "trash" ? "回收站为空" : "暂无项目");
            if (window.lucide) window.lucide.createIcons();
            return;
        }
        setStatus("共 " + items.length + " 个项目");
        for (var i = 0; i < items.length; i += 1) {
            var item = items[i];
            var node = els.projectCardTpl.content.firstElementChild.cloneNode(true);
            var openEl = node.querySelector(".open-action");
            var titleEl = node.querySelector(".project-title");
            var kindEl = node.querySelector(".kind-tag");
            var previewKindEl = node.querySelector(".preview-kind");
            var previewIconEl = node.querySelector(".preview-icon");
            var updatedEl = node.querySelector(".meta-updated");
            var nodesEl = node.querySelector(".meta-nodes");
            var ownerEl = node.querySelector(".meta-owner");
            var actionsEl = node.querySelector(".card-actions");

            node.classList.toggle("smart-project", item.kind === "smart");
            titleEl.textContent = item.title;
            kindEl.textContent = item.kind === "smart" ? "智能" : "普通";
            previewKindEl.textContent = item.kind === "smart" ? "SMART" : "CLASSIC";
            if (previewIconEl) {
                previewIconEl.setAttribute("data-lucide", item.kind === "smart" ? "sparkles" : "layout-dashboard");
            }
            updatedEl.textContent = "更新: " + toTimeText(item.updatedAt || item.createdAt);
            nodesEl.textContent = "节点: " + item.nodeCount;
            ownerEl.textContent = "Owner: " + (item.owner || "-");

            openEl.onclick = (function (x) { return function () { openProject(x); }; })(item);
            openEl.onkeydown = (function (x) {
                return function (e) {
                    if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openProject(x);
                    }
                };
            })(item);

            if (state.mode === "active") {
                actionsEl.appendChild(actionButton("打开", "arrow-up-right", "primary-btn", (function (x) {
                    return function () { openProject(x); };
                })(item)));
                actionsEl.appendChild(actionButton("重命名", "pencil", "tool-btn", (function (x) {
                    return function () { renameProject(x); };
                })(item)));
                actionsEl.appendChild(actionButton("归档", "archive", "tool-btn", (function (x) {
                    return function () { archiveProject(x); };
                })(item)));
            } else {
                actionsEl.appendChild(actionButton("恢复", "rotate-ccw", "tool-btn", (function (x) {
                    return function () { restoreProject(x); };
                })(item)));
                actionsEl.appendChild(actionButton("彻底删除", "trash", "tool-btn", (function (x) {
                    return function () { purgeProject(x); };
                })(item)));
            }
            els.projectList.appendChild(node);
        }
        if (window.lucide) window.lucide.createIcons();
    }

    async function reloadAndRender(doneText) {
        try {
            await loadProjects();
            renderList();
            if (doneText) setStatus(doneText);
        } catch (err) {
            setStatus("加载失败: " + err.message);
        }
    }

    async function bootstrap() {
        els = {
            searchInput: $("searchInput"),
            sortSelect: $("sortSelect"),
            viewToggleBtn: $("viewToggleBtn"),
            viewToggleText: $("viewToggleText"),
            newClassicBtn: $("newClassicBtn"),
            newSmartBtn: $("newSmartBtn"),
            comfyWorkbenchBtn: $("comfyWorkbenchBtn"),
            adminBtn: $("adminBtn"),
            themeToggleBtn: $("themeToggleBtn"),
            changePasswordBtn: $("changePasswordBtn"),
            logoutBtn: $("logoutBtn"),
            pageSummary: $("pageSummary"),
            activeTabBtn: $("activeTabBtn"),
            trashTabBtn: $("trashTabBtn"),
            refreshBtn: $("refreshBtn"),
            statusBar: $("statusBar"),
            activeCount: $("activeCount"),
            trashCount: $("trashCount"),
            projectList: $("projectList"),
            projectCardTpl: $("projectCardTpl"),
            passwordModal: $("passwordModal"),
            passwordForm: $("passwordForm"),
            passwordCloseBtn: $("passwordCloseBtn"),
            passwordSubmitBtn: $("passwordSubmitBtn"),
            passwordMessage: $("passwordMessage"),
            oldPasswordInput: $("oldPasswordInput"),
            newPasswordInput: $("newPasswordInput"),
        };

        var auth = window.StudioAuth ? await window.StudioAuth.guard({ requireAuth: true, redirect: true }) : { ok: true, user: null };
        if (!auth.ok) return;
        state.user = auth.user || null;

        if (state.user && state.user.is_admin) {
            els.adminBtn.classList.remove("hidden");
        }

        applyTheme(getThemeValue());

        els.searchInput.oninput = function () {
            state.query = els.searchInput.value || "";
            renderList();
        };
        els.sortSelect.onchange = function () {
            state.sort = els.sortSelect.value;
            renderList();
        };
        els.viewToggleBtn.onclick = function () {
            state.view = state.view === "grid" ? "list" : "grid";
            els.viewToggleText.textContent = state.view === "grid" ? "网格" : "列表";
            els.viewToggleBtn.querySelector("i").setAttribute("data-lucide", state.view === "grid" ? "layout-grid" : "list");
            renderList();
        };
        els.newClassicBtn.onclick = function () { createProject("classic"); };
        if (els.newSmartBtn) els.newSmartBtn.onclick = function () { createProject("smart"); };
        els.comfyWorkbenchBtn.onclick = function () { window.location.href = "/comfyui-workbench"; };
        els.adminBtn.onclick = function () { window.location.href = "/admin"; };
        els.themeToggleBtn.onclick = function () {
            var isDark = document.documentElement.classList.contains("theme-dark");
            setTheme(isDark ? "light" : "dark");
        };
        els.changePasswordBtn.onclick = function () { openPasswordModal(); };
        els.logoutBtn.onclick = function () { if (window.StudioAuth) window.StudioAuth.logout(); };
        els.activeTabBtn.onclick = function () { switchTab("active"); };
        els.trashTabBtn.onclick = function () { switchTab("trash"); };
        els.refreshBtn.onclick = function () { reloadAndRender("已刷新"); };
        if (els.passwordCloseBtn) els.passwordCloseBtn.onclick = closePasswordModal;
        if (els.passwordModal) {
            var mask = els.passwordModal.querySelector(".modal-mask");
            if (mask) mask.onclick = closePasswordModal;
        }
        if (els.passwordForm) {
            els.passwordForm.onsubmit = async function (event) {
                event.preventDefault();
                if (state.passwordSubmitting) return;
                var oldPassword = String(els.oldPasswordInput.value || "");
                var newPassword = String(els.newPasswordInput.value || "");
                if (!oldPassword || newPassword.length < 6) {
                    setPasswordMessage("请输入旧密码和至少 6 位新密码");
                    return;
                }
                if (!window.StudioAuth || typeof window.StudioAuth.changePassword !== "function") {
                    setPasswordMessage("认证模块不可用");
                    return;
                }
                state.passwordSubmitting = true;
                els.passwordSubmitBtn.disabled = true;
                setPasswordMessage("提交中...");
                try {
                    await window.StudioAuth.changePassword(oldPassword, newPassword);
                } catch (err) {
                    setPasswordMessage("修改失败: " + err.message);
                    state.passwordSubmitting = false;
                    els.passwordSubmitBtn.disabled = false;
                }
            };
        }
        window.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && els.passwordModal && !els.passwordModal.classList.contains("hidden")) {
                closePasswordModal();
            }
        });
        window.addEventListener("studio-theme-change", function (event) {
            var nextTheme = event && event.detail ? event.detail.theme : getThemeValue();
            applyTheme(nextTheme === "dark" ? "dark" : "light");
        });
        window.addEventListener("storage", function (event) {
            if (event.key === "studio_theme" || event.key === "canvas_theme") {
                applyTheme(getThemeValue());
            }
        });

        await reloadAndRender();
    }

    bootstrap();
})();
