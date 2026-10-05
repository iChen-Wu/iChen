/* ============================================================
   titlebar.js - 自绘标题栏（**仅 --frameless 时启用**）
   - 默认情况：pywebview 原生标题栏，本模块什么都不做
   - frameless：显示自绘条，提供 拖动 / 双击最大化 / 最小化 / 最大化 / 关闭

   关键：**主动向内核查询窗口模式**，不要依赖启动时注入的 window 标志——
   注入发生在页面加载之后，而这里在 DOMContentLoaded 就初始化了。

   拖动：#titlebar-drag 带 .pywebview-drag-region 类，由 pywebview 注入脚本
   原生处理（create_window 时 easy_drag=False，窗口其它区域不可拖），
   本文件不再做 JS 位移监听。
   ============================================================ */
(function () {
    const iChen = window.iChen = window.iChen || {};
    const $ = (id) => document.getElementById(id);

    let ready = false;

    async function applyMode() {
        const bar = $('titlebar');
        if (!bar) return;
        let frameless = false;
        try {
            const r = await iChen.PyAPI.getWindowMode();
            frameless = !!(r && r.frameless);
        } catch (e) {
            frameless = false;
        }
        if (!frameless) {
            bar.hidden = true;
            document.documentElement.classList.remove('frameless');
            return;
        }
        bar.hidden = false;
        document.documentElement.classList.add('frameless');
        wireOnce();
        syncState();
    }

    function wireOnce() {
        if (ready) return;
        ready = true;

        $('tb-min').addEventListener('click', () => iChen.PyAPI.windowMinimize());
        $('tb-max').addEventListener('click', onToggleClick);
        $('tb-close').addEventListener('click', () => iChen.PyAPI.windowClose());

        // 双击标题栏：最大化 / 还原（拖动本身由 pywebview 拖动区处理）
        const drag = $('titlebar-drag');
        if (drag) drag.addEventListener('dblclick', onToggleClick);
    }

    async function onToggleClick() {
        try {
            const r = await iChen.PyAPI.windowToggleMaximize();
            if (r && r.ok) setMaximized(!!r.maximized);
        } catch (e) { /* 忽略 */ }
    }

    /** 切换最大化/还原按钮图标与提示（后端状态变化也会反向推流调用此方法） */
    function setMaximized(maximized) {
        const iconMax = document.querySelector('#tb-max .tb-icon-max');
        const iconRestore = document.querySelector('#tb-max .tb-icon-restore');
        const btn = $('tb-max');
        if (iconMax) iconMax.hidden = !!maximized;
        if (iconRestore) iconRestore.hidden = !maximized;
        if (btn) btn.title = maximized ? '还原' : '最大化';
    }

    /** 初始化时向后端查一次真实状态（pywebview 的静态 maximized 属性不可信） */
    async function syncState() {
        try {
            const r = await iChen.PyAPI.windowState();
            if (r && r.ok) setMaximized(!!r.maximized);
        } catch (e) { /* 忽略 */ }
    }

    function init() {
        // 桥可能还没就绪：先试一次，再在桥就绪 / 页面加载后各试一次
        applyMode();
        document.addEventListener('ichen:bridge-ready', applyMode);
        window.addEventListener('pywebviewready', applyMode);
        window.addEventListener('load', applyMode);
    }

    iChen.Titlebar = { init, applyMode, setMaximized };
})();
