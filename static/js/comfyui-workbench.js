(function () {
    "use strict";

    var state = {
        user: null,
        instances: [],
        updatedAt: 0,
        loading: false,
    };

    var els = {};

    function $(id) { return document.getElementById(id); }

    function esc(s) {
        return String(s || "").replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[ch];
        });
    }

    function setText(el, value) {
        if (el) el.textContent = value;
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

    async function requestJson(url) {
        var res = await fetch(url, { credentials: "include", cache: "no-store" });
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

    function formatUpdatedAt(value) {
        var n = Number(value || 0);
        if (!n) return "-";
        var ms = n < 10000000000 ? n * 1000 : n;
        var d = new Date(ms);
        if (Number.isNaN(d.getTime())) return "-";
        return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    function formatLatency(value) {
        var n = Number(value);
        if (!Number.isFinite(n) || n < 0) return "-";
        return Math.round(n) + " ms";
    }

    function formatVram(item) {
        var total = Number(item && item.vram_total_mb);
        var free = Number(item && item.vram_free_mb);
        var used = Number(item && item.vram_used_mb);
        if (Number.isFinite(used) && Number.isFinite(total) && total > 0) {
            return used + " / " + total + " MB";
        }
        if (Number.isFinite(free) && Number.isFinite(total) && total > 0) {
            return "空闲 " + free + " / " + total + " MB";
        }
        if (Number.isFinite(total) && total > 0) {
            return total + " MB";
        }
        return "-";
    }

    function workerAddress(item) {
        return String((item && (item.address || item.base_url)) || "");
    }

    function workerGpu(item) {
        if (!item) return "-";
        var name = String(item.gpu || item.device_name || "").trim();
        if (name) return name;
        if (Array.isArray(item.devices) && item.devices.length) {
            var first = item.devices[0] || {};
            return String(first.name || first.type || "-");
        }
        return "-";
    }

    function setMessage(text) {
        setText(els.messageBar, text || "");
    }

    function setSummary() {
        var total = state.instances.length;
        var online = state.instances.filter(function (item) { return !!item.ok; }).length;
        var queue = state.instances.reduce(function (sum, item) {
            return sum + Number(item.queue_running || 0) + Number(item.queue_pending || 0);
        }, 0);
        setText(els.onlineCount, String(online));
        setText(els.totalCount, String(total));
        setText(els.queueCount, String(queue));
        setText(els.updatedAt, formatUpdatedAt(state.updatedAt));
        setText(els.pageSummary, total ? (online + " / " + total + " 台在线") : "未配置 ComfyUI worker");
    }

    async function copyAddress(address, btn) {
        var text = String(address || "");
        if (!text) return;
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                var input = document.createElement("textarea");
                input.value = text;
                input.setAttribute("readonly", "readonly");
                input.style.position = "fixed";
                input.style.left = "-9999px";
                document.body.appendChild(input);
                input.select();
                document.execCommand("copy");
                document.body.removeChild(input);
            }
            if (btn) {
                var old = btn.innerHTML;
                btn.innerHTML = '<i data-lucide="check" class="icon-14"></i><span>已复制</span>';
                if (window.lucide) window.lucide.createIcons();
                window.setTimeout(function () {
                    btn.innerHTML = old;
                    if (window.lucide) window.lucide.createIcons();
                }, 1200);
            }
        } catch (_e) {
            setMessage("复制失败，请手动复制: " + text);
        }
    }

    function renderWorkers() {
        els.workerList.innerHTML = "";
        setSummary();
        if (!state.instances.length) {
            setMessage("未读取到 ComfyUI worker 配置");
            if (window.lucide) window.lucide.createIcons();
            return;
        }
        setMessage("共 " + state.instances.length + " 台 worker");

        state.instances.forEach(function (item) {
            var node = els.workerCardTpl.content.firstElementChild.cloneNode(true);
            var address = workerAddress(item);
            var baseUrl = String(item.base_url || "");
            var ok = !!item.ok;

            node.classList.toggle("online", ok);
            setText(node.querySelector(".worker-address"), address || "-");
            setText(node.querySelector(".worker-reason"), ok ? (item.reason || "可连接") : (item.reason || "无法连接"));
            setText(node.querySelector(".status-pill"), ok ? "在线" : "离线");
            setText(node.querySelector(".worker-gpu"), workerGpu(item));
            setText(node.querySelector(".worker-vram"), formatVram(item));
            setText(node.querySelector(".worker-running"), String(Number(item.queue_running || 0)));
            setText(node.querySelector(".worker-pending"), String(Number(item.queue_pending || 0)));
            setText(node.querySelector(".worker-latency"), formatLatency(item.latency_ms));

            var openLink = node.querySelector(".open-link");
            if (ok && baseUrl) {
                openLink.href = baseUrl;
                openLink.title = baseUrl;
            } else {
                openLink.removeAttribute("href");
                openLink.classList.add("disabled");
                openLink.setAttribute("aria-disabled", "true");
                openLink.title = "离线 worker 暂不可打开";
            }

            var copyBtn = node.querySelector(".copy-btn");
            copyBtn.onclick = function () {
                copyAddress(baseUrl || address, copyBtn);
            };

            els.workerList.appendChild(node);
        });
        if (window.lucide) window.lucide.createIcons();
    }

    async function loadStatus(doneText) {
        if (state.loading) return;
        state.loading = true;
        if (els.refreshBtn) els.refreshBtn.disabled = true;
        setMessage("正在刷新...");
        try {
            var data = await requestJson("/api/comfyui/workbench-status");
            state.instances = Array.isArray(data.instances) ? data.instances : [];
            state.updatedAt = Number(data.updated_at || Date.now());
            if (data.user) state.user = data.user;
            if (state.user && state.user.is_admin && els.settingsBtn) {
                els.settingsBtn.classList.remove("hidden");
            }
            renderWorkers();
            if (doneText) setMessage(doneText);
        } catch (err) {
            setMessage("加载失败: " + err.message);
            setSummary();
        } finally {
            state.loading = false;
            if (els.refreshBtn) els.refreshBtn.disabled = false;
        }
    }

    async function bootstrap() {
        els = {
            backBtn: $("backBtn"),
            refreshBtn: $("refreshBtn"),
            settingsBtn: $("settingsBtn"),
            themeToggleBtn: $("themeToggleBtn"),
            pageSummary: $("pageSummary"),
            onlineCount: $("onlineCount"),
            totalCount: $("totalCount"),
            queueCount: $("queueCount"),
            updatedAt: $("updatedAt"),
            messageBar: $("messageBar"),
            workerList: $("workerList"),
            workerCardTpl: $("workerCardTpl"),
        };

        var auth = window.StudioAuth ? await window.StudioAuth.guard({ requireAuth: true, redirect: true }) : { ok: true, user: null };
        if (!auth.ok) return;
        state.user = auth.user || null;

        if (state.user && state.user.is_admin && els.settingsBtn) {
            els.settingsBtn.classList.remove("hidden");
        }

        applyTheme(getThemeValue());

        els.backBtn.onclick = function () { window.location.href = "/projects"; };
        els.refreshBtn.onclick = function () { loadStatus("已刷新"); };
        els.settingsBtn.onclick = function () { window.location.href = "/comfyui-settings"; };
        els.themeToggleBtn.onclick = function () {
            var isDark = document.documentElement.classList.contains("theme-dark");
            setTheme(isDark ? "light" : "dark");
        };

        window.addEventListener("studio-theme-change", function (event) {
            var nextTheme = event && event.detail ? event.detail.theme : getThemeValue();
            applyTheme(nextTheme === "dark" ? "dark" : "light");
        });
        window.addEventListener("storage", function (event) {
            if (event.key === "studio_theme" || event.key === "canvas_theme") {
                applyTheme(getThemeValue());
            }
        });

        await loadStatus();
    }

    bootstrap();
})();
