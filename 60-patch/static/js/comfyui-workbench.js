(function () {
    "use strict";

    var state = {
        user: null,
        instances: [],
        updatedAt: 0,
        loading: false,
        view: "workers",
        // 工作流试跑视图
        workflows: [],
        wfLoaded: false,
        wfLoading: false,
        wfFilter: "all",
        wfSearch: "",
        selectedName: "",
        selectedDetail: null,   // GET /api/workflows/{name} 的完整返回（含 config.fields）
        selectedInstance: "",   // "" = 自动调度
        fieldValues: {},
        mediaNames: {},
        mediaPreviews: {},
        running: false,
        runStartedAt: 0,
        runTimer: null,
        lastRunResult: null,
        lastRunError: "",
        importInstance: "",
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

    async function requestJson(url, options) {
        var opts = options || {};
        opts.credentials = "include";
        if (!opts.cache) opts.cache = "no-store";
        var res = await fetch(url, opts);
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

    function shortGpu(item) {
        var name = workerGpu(item);
        var m = name.match(/(RTX|GTX|Tesla|A\d{2,4}|H\d{2,4})\s*[\w\s]*?(\d{3,4}\s?(Ti)?)?/i);
        if (!m) return name === "-" ? "" : name.slice(0, 24);
        return name.replace(/^cuda:\d+\s*/i, "").replace(/\s*:\s*cudaMallocAsync.*$/i, "").slice(0, 30);
    }

    function setMessage(text) {
        setText(els.messageBar, text || "");
    }

    function setWfMessage(text) {
        setText(els.wfMessageBar, text || "");
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
            applyAdminVisibility();
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

    // ===== 工作流试跑视图 =====

    function isAdmin() {
        return !!(state.user && state.user.is_admin);
    }

    function applyAdminVisibility() {
        if (!isAdmin()) return;
        if (els.settingsBtn) els.settingsBtn.classList.remove("hidden");
        if (els.tabWorkflows) els.tabWorkflows.classList.remove("hidden");
    }

    function workflowStatus(wf) {
        if (wf.enabled) return "published";
        if (wf.last_test && wf.last_test.ok) return "tested";
        if (Number(wf.required_class_count || 0) > 0 && Number(wf.compatible_count || 0) === 0) return "missing";
        return "draft";
    }

    var STATUS_LABEL = {
        published: "已发布",
        tested: "已跑通",
        draft: "待试跑",
        missing: "缺依赖",
    };

    function switchView(view) {
        state.view = view;
        var isWorkers = view === "workers";
        els.workerView.classList.toggle("hidden", !isWorkers);
        els.workflowView.classList.toggle("hidden", isWorkers);
        els.tabWorkers.classList.toggle("active", isWorkers);
        els.tabWorkflows.classList.toggle("active", !isWorkers);
        if (!isWorkers && !state.wfLoaded) {
            loadWorkflows();
        }
    }

    async function loadWorkflows(keepSelection) {
        if (state.wfLoading) return;
        state.wfLoading = true;
        setWfMessage("正在加载工作流...");
        try {
            var data = await requestJson("/api/comfyui/workbench-workflows");
            state.workflows = Array.isArray(data.workflows) ? data.workflows : [];
            state.wfLoaded = true;
            setWfMessage("共 " + state.workflows.length + " 个工作流");
            renderWorkflowList();
            if (keepSelection && state.selectedName) {
                var still = state.workflows.find(function (w) { return w.name === state.selectedName; });
                if (!still) {
                    state.selectedName = "";
                    state.selectedDetail = null;
                    renderDetail();
                }
            }
        } catch (err) {
            setWfMessage("加载失败: " + err.message);
        } finally {
            state.wfLoading = false;
        }
    }

    function filteredWorkflows() {
        var kw = state.wfSearch.trim().toLowerCase();
        return state.workflows.filter(function (wf) {
            if (state.wfFilter !== "all" && workflowStatus(wf) !== state.wfFilter) return false;
            if (!kw) return true;
            return (String(wf.title || "") + " " + String(wf.name || "") + " " + String(wf.category || "")).toLowerCase().indexOf(kw) >= 0;
        });
    }

    function renderWorkflowList() {
        var list = filteredWorkflows();
        els.wfList.innerHTML = "";
        if (!list.length) {
            els.wfList.innerHTML = '<div class="wf-empty" style="padding:24px 0">没有匹配的工作流</div>';
            return;
        }
        list.forEach(function (wf) {
            var div = document.createElement("div");
            div.className = "wf-item" + (wf.name === state.selectedName ? " selected" : "");
            var status = workflowStatus(wf);
            var badges = '<span class="wf-badge ' + status + '">' + STATUS_LABEL[status] + "</span>";
            if (status !== "published" && wf.last_test && wf.last_test.ok) {
                badges += '<span class="wf-badge tested">已跑通</span>';
            }
            if (wf.builtin) badges += '<span class="wf-badge">内置</span>';
            if (wf.shared) badges += '<span class="wf-badge">共享盘</span>';
            var compat = Number(wf.compatible_count || 0);
            var totalInst = (wf.instances || []).length;
            badges += '<span class="wf-badge">' + compat + "/" + totalInst + " worker 可跑</span>";
            div.innerHTML =
                '<div class="wf-item-title">' + esc(wf.title || wf.name) + "</div>" +
                '<div class="wf-item-sub">' + esc(wf.name) + (wf.category ? " · " + esc(wf.category) : "") + "</div>" +
                '<div class="wf-badges">' + badges + "</div>";
            div.onclick = function () { selectWorkflow(wf.name); };
            els.wfList.appendChild(div);
        });
    }

    async function selectWorkflow(name) {
        if (state.running) {
            if (!window.confirm("当前有试跑正在进行，切换后将无法看到其结果。仍要切换吗？")) return;
        }
        state.selectedName = name;
        state.selectedDetail = null;
        state.selectedInstance = "";
        state.fieldValues = {};
        state.mediaNames = {};
        state.mediaPreviews = {};
        state.lastRunResult = null;
        state.lastRunError = "";
        renderWorkflowList();
        renderDetail();
        try {
            var data = await requestJson("/api/workflows/" + encodeURIComponent(name));
            if (state.selectedName !== name) return;
            state.selectedDetail = data;
            var fields = (data.config && data.config.fields) || [];
            fields.forEach(function (f) {
                if (f.enabled === false) return;
                if (f.default !== undefined && f.default !== null) {
                    state.fieldValues[f.id] = f.default;
                }
            });
            renderDetail();
        } catch (err) {
            if (state.selectedName !== name) return;
            els.wfDetail.innerHTML = '<div class="wf-empty">加载工作流详情失败: ' + esc(err.message) + "</div>";
        }
    }

    function selectedWorkflowItem() {
        return state.workflows.find(function (w) { return w.name === state.selectedName; }) || null;
    }

    function workerOptionMeta(addr) {
        var probe = state.instances.find(function (i) { return workerAddress(i) === addr; });
        if (!probe) return "";
        if (!probe.ok) return "离线";
        var parts = [];
        var gpu = shortGpu(probe);
        if (gpu) parts.push(gpu);
        var total = Number(probe.vram_total_mb);
        if (Number.isFinite(total) && total > 0) parts.push(Math.round(total / 1024) + "G 显存");
        parts.push("队列 " + (Number(probe.queue_running || 0) + Number(probe.queue_pending || 0)));
        return parts.join(" · ");
    }

    function renderDetail() {
        var wf = selectedWorkflowItem();
        if (!state.selectedName || !wf) {
            els.wfDetail.innerHTML = '<div class="wf-empty">在左侧选择一个工作流开始试跑</div>';
            return;
        }
        if (!state.selectedDetail) {
            els.wfDetail.innerHTML = '<div class="wf-empty">正在加载 ' + esc(wf.title || wf.name) + " ...</div>";
            return;
        }
        var cfg = state.selectedDetail.config || {};
        var fields = (cfg.fields || []).filter(function (f) { return f.enabled !== false; });
        var status = workflowStatus(wf);

        var html = "";
        html += '<div class="wf-detail-head">';
        html += '<div><h2 class="wf-detail-title">' + esc(cfg.title || wf.title || wf.name) + "</h2>";
        html += '<div class="wf-detail-name">' + esc(wf.name) + "</div>";
        html += '<div class="wf-badges" style="margin-top:6px">';
        html += '<span class="wf-badge ' + status + '">' + STATUS_LABEL[status] + "</span>";
        if (status !== "published" && wf.last_test && wf.last_test.ok) html += '<span class="wf-badge tested">已跑通</span>';
        if (wf.shared) html += '<span class="wf-badge">共享盘（只读）</span>';
        html += "</div></div>";
        html += '<div class="wf-detail-actions">';
        if (wf.enabled) {
            html += '<button id="unpublishBtn" class="tool-btn" type="button">下线（取消发布）</button>';
        } else {
            html += '<button id="publishBtn" class="primary-btn" type="button">发布到画布</button>';
        }
        html += '<button id="gotoSettingsBtn" class="tool-btn" type="button">字段映射设置</button>';
        html += "</div></div>";

        if (wf.last_test && wf.last_test.ok) {
            html += '<div class="wf-last-test">最近跑通：' + esc(formatUpdatedAt(wf.last_test.at)) +
                " · worker " + esc(wf.last_test.backend || "-") +
                (wf.last_test.by ? " · by " + esc(wf.last_test.by) : "") +
                " · 输出 " + esc(String(wf.last_test.output_count || 0)) + " 个</div>";
        }

        // worker 选择
        html += '<div class="wf-section-label">试跑 WORKER</div>';
        html += '<div class="wf-worker-select" id="workerSelect">';
        html += '<button class="wf-worker-option' + (state.selectedInstance === "" ? " selected" : "") + '" data-addr="" type="button">自动调度<span class="wf-worker-meta">按队列负载与节点兼容性选择</span></button>';
        (wf.instances || []).forEach(function (inst) {
            var classes = "wf-worker-option";
            if (state.selectedInstance === inst.address) classes += " selected";
            if (!inst.compatible) classes += " incompatible";
            var meta = "";
            if (!inst.reachable) {
                meta = "object_info 不可用";
            } else if (!inst.compatible) {
                meta = "缺 " + inst.missing_nodes.length + " 个节点";
            } else {
                meta = workerOptionMeta(inst.address) || "可运行";
            }
            html += '<button class="' + classes + '" data-addr="' + esc(inst.address) + '"' +
                (!inst.compatible ? ' title="' + esc((inst.missing_nodes || []).join(", ") || inst.error || "") + '"' : "") +
                ' type="button">' + esc(inst.address) + '<span class="wf-worker-meta">' + esc(meta) + "</span></button>";
        });
        html += "</div>";

        // 参数表单
        html += '<div class="wf-section-label">参数</div>';
        if (!fields.length) {
            html += '<div class="wf-last-test">该工作流未配置可调参数，将按 JSON 内的默认值运行。</div>';
        } else {
            html += '<div class="wf-field-grid" id="wfFieldGrid">';
            fields.forEach(function (f) {
                html += renderFieldInput(f);
            });
            html += "</div>";
        }

        // 运行栏 + 结果
        html += '<div class="wf-run-bar">';
        html += '<button id="runTestBtn" class="primary-btn" type="button"' + (state.running ? " disabled" : "") + ">" +
            (state.running ? "试跑中..." : "运行试跑") + "</button>";
        html += '<span id="runStatus" class="wf-run-status"></span>';
        html += "</div>";
        html += '<div id="runResultArea"></div>';

        els.wfDetail.innerHTML = html;
        bindDetailEvents(fields);
        renderRunResult();
        if (window.lucide) window.lucide.createIcons();
    }

    function renderFieldInput(f) {
        var type = String(f.type || "text").toLowerCase();
        var label = '<label class="wf-field-label">' + esc(f.name || f.input || f.id) +
            (f.required ? '<span class="req">*</span>' : "") +
            (f.hidden ? '<span class="hint">(发布后隐藏)</span>' : "") +
            "</label>";
        var idAttr = ' data-field="' + esc(f.id) + '"';
        var value = state.fieldValues[f.id];
        var valueStr = value === undefined || value === null ? "" : String(value);
        var cls = "wf-field";
        if (type === "textarea" || type === "image" || type === "video" || type === "audio") cls += " full";
        var inner = "";
        if (type === "textarea") {
            inner = "<textarea" + idAttr + ' placeholder="">' + esc(valueStr) + "</textarea>";
        } else if (type === "number" || type === "slider") {
            var attrs = "";
            if (f.min !== null && f.min !== undefined) attrs += ' min="' + esc(String(f.min)) + '"';
            if (f.max !== null && f.max !== undefined) attrs += ' max="' + esc(String(f.max)) + '"';
            if (f.step !== null && f.step !== undefined) attrs += ' step="' + esc(String(f.step)) + '"';
            inner = '<input type="number"' + idAttr + attrs + ' value="' + esc(valueStr) + '">';
        } else if (type === "dropdown") {
            inner = "<select" + idAttr + ">";
            (f.options || []).forEach(function (opt) {
                var sel = String(opt) === valueStr ? " selected" : "";
                inner += '<option value="' + esc(opt) + '"' + sel + ">" + esc(opt) + "</option>";
            });
            inner += "</select>";
        } else if (type === "boolean") {
            var checked = value === true || valueStr === "true" || valueStr === "1" ? " checked" : "";
            inner = '<label class="wf-media-btn"><input type="checkbox"' + idAttr + checked + "> 开启</label>";
        } else if (type === "image" || type === "video" || type === "audio") {
            var nm = state.mediaNames[f.id] || valueStr;
            var preview = "";
            if (type === "image" && state.mediaPreviews[f.id]) {
                preview = '<img class="wf-media-thumb" src="' + esc(state.mediaPreviews[f.id]) + '">';
            }
            inner = '<div class="wf-media-btn">' +
                '<button class="tool-btn media-pick-btn" type="button"' + idAttr + ' data-kind="' + esc(type) + '">选择' + (type === "image" ? "图片" : type === "video" ? "视频" : "音频") + "</button>" +
                '<span class="wf-media-name">' + esc(nm || "未选择") + "</span>" + preview + "</div>";
        } else {
            inner = '<input type="text"' + idAttr + ' value="' + esc(valueStr) + '">';
        }
        return '<div class="' + cls + '">' + label + inner + "</div>";
    }

    function bindDetailEvents(fields) {
        var workerSelect = $("workerSelect");
        if (workerSelect) {
            workerSelect.querySelectorAll(".wf-worker-option").forEach(function (btn) {
                btn.onclick = function () {
                    if (btn.classList.contains("incompatible")) return;
                    state.selectedInstance = btn.getAttribute("data-addr") || "";
                    workerSelect.querySelectorAll(".wf-worker-option").forEach(function (b) {
                        b.classList.toggle("selected", b === btn);
                    });
                };
            });
        }
        var grid = $("wfFieldGrid");
        if (grid) {
            grid.querySelectorAll("input[data-field], textarea[data-field], select[data-field]").forEach(function (input) {
                var fid = input.getAttribute("data-field");
                var handler = function () {
                    if (input.type === "checkbox") {
                        state.fieldValues[fid] = input.checked;
                    } else {
                        state.fieldValues[fid] = input.value;
                    }
                };
                input.addEventListener("input", handler);
                input.addEventListener("change", handler);
            });
            grid.querySelectorAll(".media-pick-btn").forEach(function (btn) {
                btn.onclick = function () {
                    pickMedia(btn.getAttribute("data-field"), btn.getAttribute("data-kind"));
                };
            });
        }
        var runBtn = $("runTestBtn");
        if (runBtn) runBtn.onclick = runTest;
        var publishBtn = $("publishBtn");
        if (publishBtn) publishBtn.onclick = openPublishDialog;
        var unpublishBtn = $("unpublishBtn");
        if (unpublishBtn) unpublishBtn.onclick = unpublishWorkflow;
        var gotoBtn = $("gotoSettingsBtn");
        if (gotoBtn) gotoBtn.onclick = function () {
            window.location.href = "/comfyui-settings";
        };
    }

    function mediaAccept(kind) {
        if (kind === "video") return "video/*";
        if (kind === "audio") return "audio/*";
        return "image/*";
    }

    function pickMedia(fieldId, kind) {
        var input = document.createElement("input");
        input.type = "file";
        input.accept = mediaAccept(kind);
        input.onchange = async function () {
            var file = input.files && input.files[0];
            if (!file) return;
            state.mediaNames[fieldId] = file.name + "（上传中...）";
            if (kind === "image") {
                if (state.mediaPreviews[fieldId]) URL.revokeObjectURL(state.mediaPreviews[fieldId]);
                state.mediaPreviews[fieldId] = URL.createObjectURL(file);
            }
            renderDetail();
            try {
                var form = new FormData();
                form.append("files", file);
                var res = await fetch("/api/upload", { method: "POST", body: form, credentials: "include" });
                if (!res.ok) throw new Error("上传失败");
                var data = await res.json();
                var name = (data.files && data.files[0] && (data.files[0].comfy_name || data.files[0].filename)) || file.name;
                state.fieldValues[fieldId] = name;
                state.mediaNames[fieldId] = file.name;
            } catch (e) {
                state.mediaNames[fieldId] = "上传失败，请重试";
                delete state.fieldValues[fieldId];
            }
            renderDetail();
        };
        input.click();
    }

    function setRunStatus(text, cls) {
        var el = $("runStatus");
        if (!el) return;
        el.textContent = text || "";
        el.className = "wf-run-status" + (cls ? " " + cls : "");
    }

    function startRunTimer() {
        state.runStartedAt = Date.now();
        stopRunTimer();
        state.runTimer = window.setInterval(function () {
            if (!state.running) return;
            var sec = Math.floor((Date.now() - state.runStartedAt) / 1000);
            setRunStatus("运行中... " + sec + "s（视模型大小可能需要几分钟）");
        }, 1000);
    }

    function stopRunTimer() {
        if (state.runTimer) {
            window.clearInterval(state.runTimer);
            state.runTimer = null;
        }
    }

    async function runTest() {
        if (state.running || !state.selectedName || !state.selectedDetail) return;
        var cfg = state.selectedDetail.config || {};
        var fields = (cfg.fields || []).filter(function (f) { return f.enabled !== false; });
        for (var i = 0; i < fields.length; i++) {
            var f = fields[i];
            if (f.required) {
                var v = state.fieldValues[f.id];
                if (v === undefined || v === null || String(v) === "") {
                    setRunStatus("缺少必填参数：" + (f.name || f.input || f.id), "error");
                    return;
                }
            }
        }
        state.running = true;
        state.lastRunResult = null;
        state.lastRunError = "";
        var runBtn = $("runTestBtn");
        if (runBtn) { runBtn.disabled = true; runBtn.textContent = "试跑中..."; }
        renderRunResult();
        startRunTimer();
        setRunStatus("已提交，等待 ComfyUI 执行...");
        var runName = state.selectedName;
        try {
            var res = await fetch("/api/workflows/" + encodeURIComponent(runName) + "/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({
                    fields: state.fieldValues,
                    client_id: "comfytv-test",
                    instance: state.selectedInstance || "",
                }),
            });
            var data = null;
            try { data = await res.json(); } catch (_e) {}
            if (!res.ok) {
                throw new Error((data && data.detail) || ("运行失败（HTTP " + res.status + "）"));
            }
            if (state.selectedName === runName) {
                state.lastRunResult = data;
                var sec = Math.floor((Date.now() - state.runStartedAt) / 1000);
                setRunStatus("试跑成功，用时 " + sec + "s（worker: " + (data.backend || "-") + "）", "ok");
            }
            // 刷新列表让「已跑通」徽标生效
            loadWorkflows(true);
        } catch (err) {
            if (state.selectedName === runName) {
                state.lastRunError = err.message || "运行失败";
                setRunStatus("试跑失败", "error");
            }
        } finally {
            state.running = false;
            stopRunTimer();
            var btn = $("runTestBtn");
            if (btn) { btn.disabled = false; btn.textContent = "运行试跑"; }
            renderRunResult();
        }
    }

    function renderRunResult() {
        var area = $("runResultArea");
        if (!area) return;
        if (state.lastRunError) {
            area.innerHTML = '<div class="wf-run-status error" style="white-space:pre-wrap;overflow-wrap:anywhere">' + esc(state.lastRunError) + "</div>";
            return;
        }
        var result = state.lastRunResult;
        if (!result) { area.innerHTML = ""; return; }
        var html = "";
        var images = result.images || [];
        var videos = result.videos || [];
        var others = (result.outputs || []).filter(function (u) {
            return images.indexOf(u) < 0 && videos.indexOf(u) < 0;
        });
        if (images.length || videos.length) {
            html += '<div class="wf-result-grid">';
            images.forEach(function (url) {
                html += '<img src="' + esc(url) + '" onclick="window.open(\'' + esc(url) + '\', \'_blank\')">';
            });
            videos.forEach(function (url) {
                html += '<video src="' + esc(url) + '" controls></video>';
            });
            html += "</div>";
        }
        if (others.length) {
            html += '<div class="wf-last-test">其他输出：' + others.map(function (u) {
                return '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(u.split("/").pop()) + "</a>";
            }).join(" · ") + "</div>";
        }
        if (!html) html = '<div class="wf-last-test">运行完成，但没有产生输出文件。</div>';
        area.innerHTML = html;
    }

    // ===== 从 ComfyUI 跑通记录导入 =====

    function openImportDialog() {
        els.importDialog.classList.remove("hidden");
        var addrs = state.instances.map(workerAddress).filter(Boolean);
        if (!state.importInstance || addrs.indexOf(state.importInstance) < 0) {
            state.importInstance = addrs[0] || "";
        }
        renderImportWorkerSelect();
        loadWorkerHistory();
    }

    function closeImportDialog() {
        els.importDialog.classList.add("hidden");
    }

    function renderImportWorkerSelect() {
        var html = "";
        state.instances.forEach(function (probe) {
            var addr = workerAddress(probe);
            var cls = "wf-worker-option" + (addr === state.importInstance ? " selected" : "") + (probe.ok ? "" : " incompatible");
            html += '<button class="' + cls + '" data-addr="' + esc(addr) + '" type="button">' + esc(addr) +
                '<span class="wf-worker-meta">' + esc(probe.ok ? (workerOptionMeta(addr) || "在线") : "离线") + "</span></button>";
        });
        els.importWorkerSelect.innerHTML = html;
        els.importWorkerSelect.querySelectorAll(".wf-worker-option").forEach(function (btn) {
            btn.onclick = function () {
                if (btn.classList.contains("incompatible")) return;
                state.importInstance = btn.getAttribute("data-addr") || "";
                renderImportWorkerSelect();
                loadWorkerHistory();
            };
        });
    }

    function formatHistoryTime(ms) {
        var n = Number(ms || 0);
        if (!n) return "";
        var d = new Date(n);
        if (Number.isNaN(d.getTime())) return "";
        return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    }

    async function loadWorkerHistory() {
        if (!state.importInstance) {
            els.importHistoryList.innerHTML = '<div class="wf-empty" style="padding:18px 0">没有可用的 worker</div>';
            return;
        }
        els.importHistoryList.innerHTML = '<div class="wf-empty" style="padding:18px 0">正在读取 ' + esc(state.importInstance) + ' 的运行历史...</div>';
        try {
            var data = await requestJson("/api/comfyui/worker-history?instance=" + encodeURIComponent(state.importInstance) + "&limit=30");
            renderImportHistory(Array.isArray(data.items) ? data.items : []);
        } catch (err) {
            els.importHistoryList.innerHTML = '<div class="wf-empty" style="padding:18px 0">读取失败: ' + esc(err.message) + "</div>";
        }
    }

    function renderImportHistory(items) {
        if (!items.length) {
            els.importHistoryList.innerHTML = '<div class="wf-empty" style="padding:18px 0">该 worker 还没有运行历史；先去 ComfyUI 里跑通一次工作流。</div>';
            return;
        }
        els.importHistoryList.innerHTML = "";
        items.forEach(function (item) {
            var row = document.createElement("div");
            row.className = "import-entry" + (item.success ? "" : " failed");
            var thumb = item.images && item.images.length
                ? '<img class="import-thumb" src="' + esc(item.images[0]) + '" loading="lazy">'
                : '<div class="import-thumb-empty">无输出</div>';
            var title = (item.class_types && item.class_types.length ? item.class_types.slice(0, 3).join(" / ") : "workflow");
            var time = formatHistoryTime(item.started_at_ms);
            var sub = item.node_count + " 节点 · " + (item.success ? "成功" : esc(item.status_str || "失败")) +
                (item.image_count ? " · " + item.image_count + " 输出" : "") + (time ? " · " + time : "");
            row.innerHTML = thumb +
                '<div class="import-entry-main">' +
                '<div class="import-entry-title">' + esc(title) + "</div>" +
                '<div class="import-entry-sub">' + sub + "</div>" +
                "</div>" +
                '<div class="import-entry-actions">' +
                '<input class="import-entry-name" type="text" placeholder="工作流名称" value="comfytv-' + esc(String(item.prompt_id).slice(0, 8)) + '">' +
                '<button class="primary-btn import-go-btn" type="button"' + (item.success && item.has_api_workflow ? "" : " disabled") + ">导入</button>" +
                "</div>";
            var goBtn = row.querySelector(".import-go-btn");
            var nameInput = row.querySelector(".import-entry-name");
            goBtn.onclick = function () {
                importFromHistory(item, nameInput.value, goBtn);
            };
            els.importHistoryList.appendChild(row);
        });
    }

    async function importFromHistory(item, name, btn) {
        btn.disabled = true;
        btn.textContent = "导入中...";
        try {
            var data = await requestJson("/api/comfyui/import-from-history", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    instance: state.importInstance,
                    prompt_id: item.prompt_id,
                    name: String(name || "").trim(),
                }),
            });
            closeImportDialog();
            setWfMessage("已导入「" + (data.title || data.name) + "」（自带已跑通记录），确认参数后即可发布到画布");
            await loadWorkflows(true);
            selectWorkflow(data.name);
        } catch (err) {
            window.alert("导入失败: " + err.message);
            btn.disabled = false;
            btn.textContent = "导入";
        }
    }

    // ===== 发布 =====

    function openPublishDialog() {
        if (!state.selectedDetail) return;
        var cfg = state.selectedDetail.config || {};
        var fields = (cfg.fields || []).filter(function (f) { return f.enabled !== false; });
        var box = els.publishFields;
        box.innerHTML = "";
        setText($("publishTitle"), "发布「" + (cfg.title || state.selectedName) + "」到画布");
        if (!fields.length) {
            box.innerHTML = '<div class="wf-last-test">该工作流没有配置字段映射，发布后普通用户将不可调参，仅能直接运行。</div>';
        } else {
            fields.forEach(function (f) {
                var row = document.createElement("label");
                row.className = "publish-field-row";
                var defaultStr = f.default === undefined || f.default === null ? "" : String(f.default);
                row.innerHTML = '<input type="checkbox" data-pf="' + esc(f.id) + '"' + (f.hidden ? "" : " checked") + ">" +
                    "<span>" + esc(f.name || f.input || f.id) + "</span>" +
                    '<span class="pf-type">' + esc(f.type || "text") + "</span>" +
                    (f.required ? '<span class="pf-type" style="color:var(--danger)">必填</span>' : "") +
                    '<span class="pf-default" title="' + esc(defaultStr) + '">' + esc(defaultStr) + "</span>";
                box.appendChild(row);
            });
        }
        els.publishDialog.classList.remove("hidden");
    }

    function closePublishDialog() {
        els.publishDialog.classList.add("hidden");
    }

    async function confirmPublish() {
        if (!state.selectedDetail || !state.selectedName) return;
        var btn = els.publishConfirmBtn;
        btn.disabled = true;
        btn.textContent = "发布中...";
        try {
            // 重新取一次最新 config，避免覆盖其他人的修改
            var data = await requestJson("/api/workflows/" + encodeURIComponent(state.selectedName));
            var cfg = data.config || {};
            var exposed = {};
            els.publishFields.querySelectorAll("input[data-pf]").forEach(function (cb) {
                exposed[cb.getAttribute("data-pf")] = cb.checked;
            });
            (cfg.fields || []).forEach(function (f) {
                if (Object.prototype.hasOwnProperty.call(exposed, f.id)) {
                    f.hidden = !exposed[f.id];
                }
            });
            cfg.enabled = true;
            await requestJson("/api/workflows/" + encodeURIComponent(state.selectedName) + "/config", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(cfg),
            });
            closePublishDialog();
            state.selectedDetail.config = cfg;
            setWfMessage("已发布「" + (cfg.title || state.selectedName) + "」，画布即可引用");
            await loadWorkflows(true);
            renderDetail();
        } catch (err) {
            window.alert("发布失败: " + err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = "确认发布";
        }
    }

    async function unpublishWorkflow() {
        if (!state.selectedName) return;
        if (!window.confirm("确认下线该工作流？画布中的用户将不再看到它。")) return;
        try {
            var data = await requestJson("/api/workflows/" + encodeURIComponent(state.selectedName));
            var cfg = data.config || {};
            cfg.enabled = false;
            await requestJson("/api/workflows/" + encodeURIComponent(state.selectedName) + "/config", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(cfg),
            });
            state.selectedDetail.config = cfg;
            setWfMessage("已下线「" + (cfg.title || state.selectedName) + "」");
            await loadWorkflows(true);
            renderDetail();
        } catch (err) {
            window.alert("下线失败: " + err.message);
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
            tabWorkers: $("tabWorkers"),
            tabWorkflows: $("tabWorkflows"),
            workerView: $("workerView"),
            workflowView: $("workflowView"),
            wfMessageBar: $("wfMessageBar"),
            wfFilters: $("wfFilters"),
            wfSearch: $("wfSearch"),
            wfList: $("wfList"),
            wfDetail: $("wfDetail"),
            publishDialog: $("publishDialog"),
            publishFields: $("publishFields"),
            publishConfirmBtn: $("publishConfirmBtn"),
            publishCancelBtn: $("publishCancelBtn"),
            importFromComfyBtn: $("importFromComfyBtn"),
            importDialog: $("importDialog"),
            importWorkerSelect: $("importWorkerSelect"),
            importHistoryList: $("importHistoryList"),
            importCancelBtn: $("importCancelBtn"),
        };

        var auth = window.StudioAuth ? await window.StudioAuth.guard({ requireAuth: true, redirect: true }) : { ok: true, user: null };
        if (!auth.ok) return;
        state.user = auth.user || null;
        applyAdminVisibility();

        applyTheme(getThemeValue());

        els.backBtn.onclick = function () { window.location.href = "/projects"; };
        els.refreshBtn.onclick = function () {
            if (state.view === "workers") {
                loadStatus("已刷新");
            } else {
                loadStatus();
                loadWorkflows(true);
            }
        };
        els.settingsBtn.onclick = function () { window.location.href = "/comfyui-settings"; };
        els.themeToggleBtn.onclick = function () {
            var isDark = document.documentElement.classList.contains("theme-dark");
            setTheme(isDark ? "light" : "dark");
        };

        els.tabWorkers.onclick = function () { switchView("workers"); };
        els.tabWorkflows.onclick = function () { switchView("workflows"); };

        els.wfFilters.querySelectorAll(".wf-chip").forEach(function (chip) {
            chip.onclick = function () {
                state.wfFilter = chip.getAttribute("data-filter") || "all";
                els.wfFilters.querySelectorAll(".wf-chip").forEach(function (c) {
                    c.classList.toggle("active", c === chip);
                });
                renderWorkflowList();
            };
        });
        els.wfSearch.oninput = function () {
            state.wfSearch = els.wfSearch.value || "";
            renderWorkflowList();
        };

        els.publishCancelBtn.onclick = closePublishDialog;
        els.publishConfirmBtn.onclick = confirmPublish;
        els.publishDialog.addEventListener("click", function (e) {
            if (e.target === els.publishDialog) closePublishDialog();
        });

        els.importFromComfyBtn.onclick = openImportDialog;
        els.importCancelBtn.onclick = closeImportDialog;
        els.importDialog.addEventListener("click", function (e) {
            if (e.target === els.importDialog) closeImportDialog();
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

        await loadStatus();
    }

    bootstrap();
})();
