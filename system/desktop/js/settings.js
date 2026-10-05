/* ============================================================
   settings.js - 控制台 → 设置
   主题 / Tab 栏位置：持久化到 data/local_config.json（经 Python 桥），
   浏览器预览（无桥）时降级用 localStorage。
   状态行（版本 / App 总数）/ 最近通知 / 退出应用。
   App 与文件夹的增删改已移到控制台 →「App 管理」（appmgmt.js）。
   ============================================================ */
(function () {
    const iChen = window.iChen = window.iChen || {};
    const $ = (id) => document.getElementById(id);

    const THEME_KEY = 'ichen-theme';

    function store(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
    }
    function load(key, def) {
        try { return localStorage.getItem(key) ?? def; } catch (e) { return def; }
    }

    /* ---------- 主题 ---------- */
    function applyTheme(theme) {
        const t = (theme === 'light' || theme === 'dark') ? theme : 'system';
        document.documentElement.dataset.theme = t;
        document.querySelectorAll('#theme-options .theme-option').forEach((b) => {
            b.classList.toggle('active', b.dataset.themeOption === t);
        });
        // 主题下传 App iframe（接入规范第八节 6）
        if (iChen.AppFrame && iChen.AppFrame.broadcastTheme) iChen.AppFrame.broadcastTheme();
    }

    function setTheme(theme) {
        applyTheme(theme);
        store(THEME_KEY, theme);
        // 持久化到 data/local_config.json（下次启动由 Python 侧读回）
        iChen.PyAPI.saveLocalConfig({ theme: theme }).catch(() => { /* 离线预览时忽略 */ });
    }

    /* ---------- Tab 栏位置（持久化到 data/local_config.json） ---------- */
    function applyTabbarPosition(pos) {
        const p = (pos === 'bottom') ? 'bottom' : 'left';
        document.documentElement.dataset.tabbar = p;
        document.querySelectorAll('#tabbar-options .theme-option').forEach((b) => {
            b.classList.toggle('active', b.dataset.tabbarOption === p);
        });
    }

    function setTabbarPosition(pos) {
        applyTabbarPosition(pos);
        iChen.PyAPI.saveLocalConfig({ tabbar_position: pos }).catch(() => { /* 忽略 */ });
    }

    /* ---------- 无边框窗口开关（持久化到 local_config，重启后生效） ---------- */
    // 当前实例的真实窗口模式（唯一门禁，来自后端 getWindowMode），开关初始态只认它
    let currentFrameless = false;

    function setFramelessSwitch(on) {
        const btn = $('frameless-switch');
        if (btn) btn.setAttribute('aria-checked', on ? 'true' : 'false');
    }

    function syncFramelessSwitch() {
        return iChen.PyAPI.getWindowMode().then((r) => {
            currentFrameless = !!(r && r.frameless);
            setFramelessSwitch(currentFrameless);
            const row = $('frameless-restart-row');
            if (row) row.hidden = true;   // 重新同步 = 无待生效改动
        }).catch(() => { /* 忽略：保持默认关闭态 */ });
    }

    function onFramelessToggle() {
        const btn = $('frameless-switch');
        if (!btn) return;
        const next = btn.getAttribute('aria-checked') !== 'true';
        setFramelessSwitch(next);   // 先给视觉反馈，保存失败再回滚
        iChen.PyAPI.saveLocalConfig({ frameless: next }).then((r) => {
            if (r && r.status === 'error') throw new Error(r.message || '保存失败');
            const row = $('frameless-restart-row');
            if (row) row.hidden = false;
            if (iChen.Notify) iChen.Notify.info('无边框窗口设置已保存，重启后生效');
        }).catch((e) => {
            setFramelessSwitch(currentFrameless);
            if (iChen.Notify) iChen.Notify.error('设置保存失败：' + (e && e.message ? e.message : e));
        });
    }

    /* ---------- 状态行 ---------- */
    async function loadStatus() {
        try {
            const info = await iChen.PyAPI.getSystemInfo();
            $('settings-version').textContent = info.version || '—';
        } catch (e) {
            $('settings-version').textContent = '—';
        }
        try {
            const r = await iChen.PyAPI.scanApps();
            $('settings-app-count').textContent = (r && typeof r.app_count === 'number') ? String(r.app_count) : '—';
        } catch (e) {
            $('settings-app-count').textContent = '—';
        }
    }

    /* ---------- 最近通知（控制台历史；来源见 notify.js） ---------- */
    function fmtTime(ts) {
        const d = new Date(ts);
        const p = (n) => (n < 10 ? '0' + n : '' + n);
        return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
    }

    async function copyText(text, btn) {
        let ok = false;
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text);
                ok = true;
            }
        } catch (e) { /* 退回 execCommand */ }
        if (!ok) {
            try {
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.cssText = 'position:fixed;opacity:0';
                document.body.appendChild(ta);
                ta.select();
                ok = document.execCommand('copy');
                ta.remove();
            } catch (e) { ok = false; }
        }
        if (btn) {
            const old = btn.textContent;
            btn.textContent = ok ? '已复制' : '复制失败';
            btn.disabled = true;
            setTimeout(() => { btn.textContent = old; btn.disabled = false; }, 1200);
        }
    }

    function renderNotify() {
        const box = $('notify-list');
        if (!box || !iChen.Notify) return;
        const list = iChen.Notify.history();
        if (!list.length) {
            box.innerHTML = '<div class="app-manage-empty">本次运行还没有通知</div>';
            return;
        }
        box.innerHTML = '';
        list.forEach((n) => {
            const row = document.createElement('div');
            row.className = 'settings-row notify-row notify-' + n.level;
            const t = document.createElement('span');
            t.className = 'settings-label';
            t.textContent = fmtTime(n.ts);
            const v = document.createElement('span');
            v.className = 'settings-value';
            v.textContent = n.text;
            const copyBtn = document.createElement('button');
            copyBtn.type = 'button';
            copyBtn.className = 'btn notify-copy-btn';
            copyBtn.textContent = '复制';
            copyBtn.title = '复制通知内容';
            copyBtn.addEventListener('click', () => copyText(n.text, copyBtn));
            row.appendChild(t);
            row.appendChild(v);
            row.appendChild(copyBtn);
            box.appendChild(row);
        });
    }

    /* ---------- init ---------- */
    // 主题 / Tab 栏位置：优先读 data/local_config.json（跨设备保留），
    // 读不到再退回 localStorage（浏览器预览或首次启动）。
    function loadAndApplyConfig() {
        return iChen.PyAPI.getLocalConfig().then((c) => {
            const cfg = c || {};
            applyTabbarPosition(cfg.tabbar_position || 'left');
            applyTheme(cfg.theme || load(THEME_KEY, 'system'));
        }).catch(() => {
            applyTabbarPosition('left');
            applyTheme(load(THEME_KEY, 'system'));
        });
    }

    iChen.Settings = {
        init() {
            loadAndApplyConfig();
            syncFramelessSwitch();
            // 桥注入晚于 DOMContentLoaded：首次读取拿到的是兜底 {}，
            // 桥就绪后必须重读一次，否则持久化的主题/Tab 位置看似"没保存"
            document.addEventListener('ichen:bridge-ready', () => {
                loadAndApplyConfig();
                syncFramelessSwitch();
            });

            document.querySelectorAll('#theme-options .theme-option').forEach((b) => {
                b.addEventListener('click', () => setTheme(b.dataset.themeOption));
            });
            document.querySelectorAll('#tabbar-options .theme-option').forEach((b) => {
                b.addEventListener('click', () => setTabbarPosition(b.dataset.tabbarOption));
            });

            // 无边框窗口开关 + 立即重启
            const flBtn = $('frameless-switch');
            if (flBtn) flBtn.addEventListener('click', onFramelessToggle);
            const restartBtn = $('frameless-restart-btn');
            if (restartBtn) restartBtn.addEventListener('click', () => {
                restartBtn.disabled = true;
                iChen.PyAPI.restartApp().then((r) => {
                    if (r && r.status === 'error') {
                        restartBtn.disabled = false;
                        if (iChen.Notify) iChen.Notify.error('重启失败：' + (r.message || ''));
                    }
                    // 成功时进程即将退出，无需复位按钮
                }).catch((e) => {
                    restartBtn.disabled = false;
                    if (iChen.Notify) iChen.Notify.error('重启失败：' + e);
                });
            });

            // 系统主题变化（theme=system 时）同步 App iframe
            try {
                const mq = window.matchMedia('(prefers-color-scheme: dark)');
                mq.addEventListener('change', () => {
                    const cur = document.documentElement.dataset.theme;
                    if (cur === 'system') applyTheme('system');
                });
            } catch (e) { /* 忽略 */ }

            loadStatus();

            // 设置面板被打开时刷新状态（控制台 → 设置条目）
            document.addEventListener('ichen:zone-changed', (e) => {
                if (e.detail && (e.detail.panel === 'settings' || e.detail.zone === 'settings')) {
                    loadStatus();
                    renderNotify();
                    syncFramelessSwitch();
                }
            });

            $('settings-quit').addEventListener('click', () => { iChen.PyAPI.quitApp(); });

            // 最近通知
            if (iChen.Notify) {
                iChen.Notify.onChange(renderNotify);
                const clearBtn = $('btn-notify-clear');
                if (clearBtn) clearBtn.addEventListener('click', () => iChen.Notify.clear());
            }
            renderNotify();
        },
    };
})();
