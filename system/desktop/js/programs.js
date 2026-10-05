/* ============================================================
   programs.js - 控制台"程序"面板：运行中的程序实例（手机后台式任务卡）
   - 数据来自 AppFrame 的实例表（打开即常驻，切走挂后台）
   - 操作：切到前台 / 终止（销毁实例）
   ============================================================ */
(function () {
    const iChen = window.iChen = window.iChen || {};
    const $ = (id) => document.getElementById(id);

    const DEFAULT_ICON = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        + '<rect x="8" y="8" width="48" height="48" rx="12" fill="#dbe7fb"/></svg>')));

    function fmtTime(ts) {
        const d = new Date(ts);
        const p = (n) => (n < 10 ? '0' + n : '' + n);
        return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
    }

    function render() {
        const box = $('program-cards');
        if (!box) return;
        const list = (iChen.AppFrame && iChen.AppFrame.list) ? iChen.AppFrame.list() : [];
        const empty = $('programs-empty');
        if (empty) empty.hidden = list.length > 0;

        box.innerHTML = '';
        list.forEach((p) => {
            const card = document.createElement('div');
            card.className = 'program-card' + (p.active ? ' active' : '');

            const head = document.createElement('div');
            head.className = 'pc-head';
            const img = document.createElement('img');
            img.className = 'pc-icon';
            img.src = p.icon || DEFAULT_ICON;
            img.alt = '';
            const meta = document.createElement('div');
            meta.className = 'pc-meta';
            const name = document.createElement('div');
            name.className = 'pc-name';
            name.textContent = p.name;
            const sub = document.createElement('div');
            sub.className = 'pc-sub';
            sub.textContent = (p.zone ? p.zone + ' · ' : '') + '启动 ' + fmtTime(p.opened_at)
                + (p.active ? ' · 前台' : ' · 后台');
            meta.appendChild(name);
            meta.appendChild(sub);
            head.appendChild(img);
            head.appendChild(meta);

            const actions = document.createElement('div');
            actions.className = 'pc-actions';

            const front = document.createElement('button');
            front.className = 'btn';
            front.textContent = '切到前台';
            front.disabled = !!p.active;
            front.addEventListener('click', () => {
                if (iChen.Shell && p.zone) iChen.Shell.activate(p.zone); // Tab 同步
                if (iChen.AppFrame) {
                    ['settings-view', 'processes-view', 'welcome-view', 'appmgmt-view', 'automation-view'].forEach((id) => {
                        const el = $(id);
                        if (el) el.hidden = true;
                    });
                    $('stage-placeholder').hidden = true;
                    iChen.AppFrame.show(p.id);
                }
                render();
            });

            const kill = document.createElement('button');
            kill.className = 'btn btn-danger';
            kill.textContent = '终止';
            kill.addEventListener('click', async () => {
                if (!await iChen.Dialog.confirm('终止「' + p.name + '」？该程序将结束运行，未保存的数据会丢失。', '确认终止')) return;
                kill.disabled = true;
                kill.textContent = '终止中…';
                if (iChen.AppFrame) await iChen.AppFrame.terminate(p.id);
                if (iChen.UI) iChen.UI.showToast('已终止：' + p.name);
                render();
            });

            actions.appendChild(front);
            actions.appendChild(kill);
            card.appendChild(head);
            card.appendChild(actions);
            box.appendChild(card);
        });
    }

    iChen.Programs = {
        init() {
            const b = $('btn-programs-refresh');
            if (b) b.addEventListener('click', render);
            // 实例增减 / 前后台变化时，若面板可见则刷新
            document.addEventListener('ichen:instances-changed', () => {
                const view = $('processes-view');
                if (view && !view.hidden) render();
            });
            document.addEventListener('ichen:instance-shown', () => {
                const view = $('processes-view');
                if (view && !view.hidden) render();
            });
        },
        render,
    };
})();
