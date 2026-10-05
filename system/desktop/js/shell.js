/* ============================================================
   shell.js - 主壳状态机（动态主体）
   - 主体（Tab）由 apps/ 一级目录动态生成（scan_zones；folder.json 提供
     名称/图标/顺序）——apps 里新增一级文件夹，刷新后 Tab 自动出现
   - 底部固定"控制台"：其列表是控制台条目（设置为其一，可扩展日志/关于等）
   - 列表开关固定在顶部状态栏左侧；无待机层（待机将来由程序承担）
   ============================================================ */
(function () {
    const iChen = window.iChen = window.iChen || {};

    const state = {
        zones: [],          // [{key,name,icon_data,order,...}]
        zone: null,         // 当前主体 key（分区路径 或 'console'）
        item: null,         // 控制台当前条目 key
        collapsed: false,   // 列表区折叠
    };

    const $ = (id) => document.getElementById(id);

    /** 复制文本到剪贴板：优先 Clipboard API，失败降级 execCommand（WebView2 / 非安全上下文） */
    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (e) {
            try {
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                const ok = document.execCommand('copy');
                document.body.removeChild(ta);
                return ok;
            } catch (e2) { return false; }
        }
    }

    /** 接入页：把完整开发规格填入折叠预览，并绑定「复制给 AI」按钮
     *
     * 规格原文不再内嵌在 index.html 里（那段文本含 </style> </script> </body> </html>，
     * 浏览器按 RCDATA 没事，但 VS Code 的 HTML 语言服务会当真实标签而报错），
     * 改由 js/welcome-doc.js 提供 window.__ICHEN_WELCOME_DOC__。
     */
    function initWelcomeDoc() {
        const view = $('welcome-doc-view');
        const btn = $('welcome-copy-doc');
        if (!view || !btn) return;
        const doc = String(window.__ICHEN_WELCOME_DOC__ || '').trim();
        if (!doc) {
            view.textContent = '（未找到规格原文：请确认 js/welcome-doc.js 已加载）';
            btn.disabled = true;
            return;
        }
        view.textContent = doc;
        btn.addEventListener('click', async () => {
            const oldText = btn.textContent;
            const ok = await copyText(doc);
            btn.textContent = ok ? '已复制，直接粘贴发给 AI 即可' : '复制失败，请展开下方预览手动复制';
            if (!ok) btn.classList.remove('btn-primary');
            setTimeout(() => {
                btn.textContent = oldText;
                btn.classList.add('btn-primary');
            }, 1600);
        });
    }

    // 统一 base64 data URI（避免 utf8 data URI 在部分 WebView 下的解析差异）
    const svgUri = (svg) => 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)));

    const DEFAULT_TAB_ICON = svgUri(
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        + '<rect x="8" y="8" width="48" height="48" rx="12" fill="#dbe7fb"/></svg>');

    // 控制台条目：接入（说明）/ 后台（运行中的实例）/ 自动化 / 设置
    const CONSOLE_ITEMS = [
        {
            key: 'welcome', name: '接入', panel: 'welcome',
            icon: svgUri('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
                + '<circle cx="32" cy="32" r="22" fill="none" stroke="#7c8aa5" stroke-width="4"/>'
                + '<path d="M32 28 v16" stroke="#7c8aa5" stroke-width="5" stroke-linecap="round"/>'
                + '<circle cx="32" cy="20" r="3" fill="#7c8aa5"/></svg>'),
        },
        {
            key: 'programs', name: '后台', panel: 'programs',
            icon: svgUri('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
                + '<rect x="7" y="9" width="34" height="28" rx="6" fill="none" stroke="#8fa3c0" stroke-width="4"/>'
                + '<rect x="21" y="22" width="36" height="30" rx="6" fill="#dbe7fb" stroke="#7c8aa5" stroke-width="4"/></svg>'),
        },
        {
            key: 'appmgmt', name: 'App 管理', panel: 'appmgmt',
            icon: svgUri('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
                + '<rect x="10" y="16" width="44" height="34" rx="6" fill="none" stroke="#7c8aa5" stroke-width="4"/>'
                + '<path d="M10 26h44" stroke="#7c8aa5" stroke-width="4"/>'
                + '<circle cx="18" cy="21" r="2.5" fill="#7c8aa5"/></svg>'),
        },
        {
            key: 'automation', name: '自动化', panel: 'automation',
            icon: svgUri('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
                + '<circle cx="32" cy="32" r="8" fill="none" stroke="#7c8aa5" stroke-width="4"/>'
                + '<path d="M32 12 v8 M32 44 v8 M12 32 h8 M44 32 h8" stroke="#7c8aa5" stroke-width="4" stroke-linecap="round"/>'
                + '<circle cx="32" cy="32" r="22" fill="none" stroke="#aebbd0" stroke-width="3" stroke-dasharray="4 6"/></svg>'),
        },
        {
            key: 'settings', name: '设置', panel: 'settings',
            icon: svgUri('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
                + '<circle cx="32" cy="32" r="11" fill="none" stroke="#7c8aa5" stroke-width="5"/>'
                + '<g stroke="#7c8aa5" stroke-width="5" stroke-linecap="round">'
                + '<line x1="32" y1="8" x2="32" y2="15"/><line x1="32" y1="49" x2="32" y2="56"/>'
                + '<line x1="8" y1="32" x2="15" y2="32"/><line x1="49" y1="32" x2="56" y2="32"/></g></svg>'),
        },
    ];

    /* ================= 主体（分区 Tab） ================= */
    async function loadZones() {
        try {
            const r = await iChen.PyAPI.scanZones();
            state.zones = (r && r.zones) || [];
        } catch (e) {
            state.zones = [];
        }
        renderZoneTabs();
        return state.zones;
    }

    function renderZoneTabs() {
        const box = $('zone-tabs');
        if (!box) return;
        box.innerHTML = '';
        (state.zones || []).forEach((z) => {
            const b = document.createElement('button');
            b.className = 'tab zone-tab';
            b.dataset.zone = z.key;
            if (state.zone === z.key) b.classList.add('active');
            b.title = z.description ? (z.name + ' · ' + z.description) : z.name;
            const img = document.createElement('img');
            img.className = 'tab-icon';
            img.src = z.icon_data || DEFAULT_TAB_ICON;
            img.alt = '';
            const s = document.createElement('span');
            // 名称宽度固定：≤3 字原样；>3 字显示"前 2 字 + …"（保证各 Tab 布局一致）
            const chars = Array.from(z.name || z.key || '');
            s.textContent = chars.length <= 3 ? chars.join('') : chars.slice(0, 2).join('') + '…';
            s.title = chars.join('');
            b.appendChild(img);
            b.appendChild(s);
            b.addEventListener('click', () => { clickZone(z.key); });
            box.appendChild(b);
        });
    }

    /** 点击主体 Tab：先重扫分区元数据（Tab 栏自身的名称/图标也一起刷新），再激活 */
    async function clickZone(key) {
        await loadZones();
        if ((state.zones || []).some((x) => x.key === key)) {
            activate(key);
        } else {
            await reload(); // 分区刚被改名/删除 → 走回退逻辑
        }
    }

    function setTabActive(key) {
        document.querySelectorAll('#tabbar .tab').forEach((t) => {
            t.classList.toggle('active', t.dataset.zone === key);
        });
    }

    /** 激活一个主体（分区 key 或 'console'） */
    function activate(key) {
        if (key === 'console') { activateConsole(); return; }
        const z = (state.zones || []).find((x) => x.key === key);
        if (!z) return;
        state.collapsed = false; // 点击主体 Tab：若列表处于折叠则自动展开
        state.zone = key;
        state.item = null;
        setTabActive(key);

        // 列表区（折叠走 CSS 过渡，不用 display:none）
        syncPaneClass();
        $('listpane-title').textContent = z.name;

        // 内容：面板全部隐藏（保留 App 实例，后台挂起）
        hidePanels();
        if (iChen.AppFrame) iChen.AppFrame.showForZone(key); // 该分区上次运行的程序（没有则占位）

        // 渲染该分区的目录树
        if (iChen.Tree) iChen.Tree.refreshForZone(key, z.name);
        syncPaneToggle();
        document.dispatchEvent(new CustomEvent('ichen:zone-changed', { detail: { zone: key, zoneName: z.name } }));
    }

    /* ================= 控制台（设置等条目） ================= */
    async function activateConsole() {
        state.collapsed = false;
        state.zone = 'console';
        setTabActive('console');

        syncPaneClass();
        $('listpane-title').textContent = '控制台';

        renderConsoleList();

        // 默认选中第一个条目（后台）
        const first = CONSOLE_ITEMS.length ? CONSOLE_ITEMS[0].key : null;
        selectConsoleItem(first);
        syncPaneToggle();
    }

    function renderConsoleList() {
        const root = $('app-tree');
        root.innerHTML = '';
        $('tree-empty').hidden = true;

        CONSOLE_ITEMS.forEach((item) => {
            const row = document.createElement('div');
            row.className = 'trow trow-app console-item';
            row.dataset.kind = 'console';
            row.dataset.key = item.key;
            if (state.item === item.key) row.classList.add('active');

            const arrow = document.createElement('span');
            arrow.className = 'spacer-arrow';

            const img = document.createElement('img');
            img.className = 'trow-icon';
            img.src = item.icon || DEFAULT_TAB_ICON;
            img.alt = '';

            const name = document.createElement('span');
            name.className = 'trow-name';
            name.textContent = item.name;

            row.appendChild(arrow);
            row.appendChild(img);
            row.appendChild(name);
            row.addEventListener('click', () => selectConsoleItem(item.key));
            root.appendChild(row);
        });
    }

    function hidePanels() {
        $('settings-view').hidden = true;
        $('processes-view').hidden = true;
        $('welcome-view').hidden = true;
        $('appmgmt-view').hidden = true;
        $('automation-view').hidden = true;
    }

    function selectConsoleItem(key) {
        const item = CONSOLE_ITEMS.find((x) => x.key === key);
        if (!item) return;

        state.item = key;
        document.querySelectorAll('#app-tree .console-item').forEach((r) => {
            r.classList.toggle('active', r.dataset.key === key);
        });

        // 隐藏所有程序实例（后台挂起、不销毁）
        if (iChen.AppFrame) iChen.AppFrame.hideAll();

        const panelKey = item.panel;
        $('settings-view').hidden = (panelKey !== 'settings');
        $('processes-view').hidden = (panelKey !== 'programs');
        $('welcome-view').hidden = (panelKey !== 'welcome');
        $('appmgmt-view').hidden = (panelKey !== 'appmgmt');
        $('automation-view').hidden = (panelKey !== 'automation');
        $('stage-placeholder').hidden = true;

        if (panelKey === 'programs' && iChen.Programs) iChen.Programs.render();
        if (panelKey === 'appmgmt' && iChen.AppMgmt) iChen.AppMgmt.render();
        if (panelKey === 'automation' && iChen.Automation) iChen.Automation.render();

        // 面板淡入
        const panelMap = {
            settings: $('settings-view'),
            programs: $('processes-view'),
            welcome: $('welcome-view'),
            appmgmt: $('appmgmt-view'),
            automation: $('automation-view'),
        };
        const panel = panelMap[panelKey] || null;
        if (panel && iChen.UI) iChen.UI.animateIn(panel);

        document.dispatchEvent(new CustomEvent('ichen:zone-changed', {
            detail: { zone: 'console', panel: panelKey },
        }));
    }

    /** 手动刷新：重扫 zones（新增/删除一级文件夹 → Tab 变化）并刷新当前视图 */
    async function reload() {
        await loadZones();
        if (state.zone === 'console') { renderConsoleList(); return; }
        const current = state.zone && state.zone !== 'console';
        if (current && !(state.zones || []).some((z) => z.key === state.zone)) {
            state.zone = null; // 当前分区已被删除/不存在 → 回退
        }
        const fallback = (state.zones && state.zones.length) ? state.zones[0].key : 'console';
        activate(state.zone || fallback);
    }

    /* ================= 列表开关（固定顶部状态栏左侧） ================= */
    function syncPaneClass() {
        $('shell-row').classList.toggle('collapsed', state.collapsed);
    }

    function syncPaneToggle() {
        const on = !state.collapsed;
        const btn = $('btn-pane-toggle');
        if (!btn) return;
        btn.classList.toggle('active', on);
        btn.setAttribute('aria-expanded', String(on));
    }

    function togglePane() {
        state.collapsed = !state.collapsed;
        syncPaneClass(); // CSS 过渡：滑出/滑入
        syncPaneToggle();
        $('btn-pane-toggle').title = state.collapsed ? '显示列表' : '隐藏列表';
    }

    /* ================= 暴露 ================= */
    iChen.Shell = {
        getZone: () => state.zone,
        getZones: () => state.zones,
        activate,
        activateConsole,
        selectConsoleItem,
        reload,
        togglePane,
    };

    /* ================= 事件绑定 ================= */
    document.addEventListener('DOMContentLoaded', () => {
        $('btn-pane-toggle').addEventListener('click', togglePane);
        $('tab-console').addEventListener('click', () => activateConsole());

        // 接入页：规格预览填充 + 一键复制绑定
        initWelcomeDoc();

        // 启动即自动扫描 apps/（重扫分区 → 激活首个分区 → 加载其目录树），
        // 新增 / 删除文件夹后重开中枢即可见，无需手动刷新。
        reload().catch(() => {
            activate('console');
        });

        // pywebview 的 js_api 注入晚于 DOMContentLoaded：首次扫描大概率拿到
        // "未连接桥" 的空结果。桥就绪后若分区仍为空则自动重扫一次（替代原刷新按钮）。
        document.addEventListener('ichen:bridge-ready', () => {
            if (!(state.zones || []).length) reload().catch(() => {});
        });
    });
})();
