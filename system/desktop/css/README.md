# desktop/css 副本说明

本目录的 `tokens.css` 与 `components.css` 是项目根 `shared/common/css/` 的**运行副本**。

原因：`index.html` 以 file:// 打开时，跨目录 `../shared/...` 引用在部分
WebView（pywebview/WebView2）下加载不可靠，导致样式令牌全部失效（直角、无玻璃）。

- **唯一来源**：`shared/common/css/`（App 样式注入 `get_shared_css()` 也从那里读）
- **运行副本**：本目录，供 `index.html` 同目录 `<link>` 使用
- 修改样式请改 `shared/common/css/` 后同步复制到本目录（一致性测试 `tests/test_css_sync.py` 会拦漂移）
