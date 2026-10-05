/* ============================================================
   notify.js - 通知中心：状态栏 toast + 控制台历史
   - push(level, text)        记录并提示（level: info | warn | error）
   - history()                取最近记录（新在前）
   - onChange(fn)             记录变化时回调（控制台渲染用）
   - 来源：服务崩溃 / 端口占用 / App 挂载失败 等
   历史只放内存（不上磁盘），重启即清空——它反映的是"本次运行发生了什么"。
   ============================================================ */
(function () {
    const iChen = window.iChen = window.iChen || {};

    const MAX = 100;
    const items = [];          // [{level, text, ts}]
    const listeners = [];

    function push(level, text) {
        const item = {
            level: (level === 'error' || level === 'warn') ? level : 'info',
            text: String(text == null ? '' : text),
            ts: Date.now(),
        };
        items.unshift(item);
        if (items.length > MAX) items.length = MAX;

        // 状态栏 toast（复用 ui.js 的实现）
        if (iChen.UI && iChen.UI.showToast) {
            const prefix = item.level === 'error' ? '✕ ' : (item.level === 'warn' ? '! ' : '');
            iChen.UI.showToast(prefix + item.text);
        }

        listeners.forEach((fn) => {
            try { fn(item); } catch (e) { /* 忽略 */ }
        });
        document.dispatchEvent(new CustomEvent('ichen:notify', { detail: item }));
        return item;
    }

    function clear() {
        items.length = 0;
        listeners.forEach((fn) => { try { fn(null); } catch (e) { /* 忽略 */ } });
    }

    iChen.Notify = {
        push,
        info: (t) => push('info', t),
        warn: (t) => push('warn', t),
        error: (t) => push('error', t),
        history: () => items.slice(),
        clear,
        onChange(fn) { if (typeof fn === 'function') listeners.push(fn); },
    };
})();
