# iChen 项目说明

## 一、它是什么

iChen 是一个**个人操作系统**：让 py、html 这类小文件程序有一个集成的中枢——发现、挂载、调度、
生命周期由系统统一承担。写一个 App 就是按规范放一个文件夹（`manifest.json` + `ui/` + `core.py`），
即写即用，类似 APK 的体验；桌面界面负责聚合与调度，程序常驻托盘。

## 二、三个版本（边界必须分清）

| 版本 | 路径 | 用途 | 运行方式 |
|---|---|---|---|
| **开发版（中枢工作区）** | `d:\workspace\iChen` | 中枢开发地；apps 只留测试用夹具 | `python -m system.main`（Python 3.14，D:\download\python） |
| **正式版** | `D:\iChen` | 日常使用；全部业务 App、业务库、业务数据都在这 | 快捷方式 iChen.lnk → `pythonw.exe -m main`（系统 Python） |
| **移动版** | `F:\iChen` | U 盘随身；自带 runtime，不装业务 App | 根目录 `iChen.exe` / `pythonw.exe main.py` |

- 移动版整盘备份在 `D:\workspace\iChen移动端`（1291 文件，哈希校验一致）。
- 三个版本的 `apps/`、`shared/` 内容**故意不同**，不要互相覆盖。详见《数据与备份说明》。

## 三、目录结构（开发版）

```
iChen/
├── main.py            # 交付版启动器（找 Python / 查 WebView2 → 交给 system.main）
├── system/            # 系统中枢（常驻进程，托盘运行）
│   ├── main.py        # 真正的入口（开发版 python -m system.main）
│   ├── desktop/       # 桌面界面：index.html、css/、js/
│   ├── kernel/        # 内核：api.py（Mixin 组合）、settings、window、tray
│   └── apphost/       # App 宿主：apps.py（扫描/运行）、app_edit.py
├── shared/            # 无进程的共享库
│   ├── GYun/          # 数据 / LLM 地基（SQLite 实体库 + 客户端）
│   ├── BYu/           # 业务库（班级/积分/歌曲等）
│   └── common/        # 中立层：paths.py（路径常量唯一来源）、css/（公共样式唯一来源）
├── apps/              # App 内容根：work/（人用）、space/（智能体侧）——本仓库只留测试夹具
├── docs/              # 项目文档（本目录）
├── data/              # 运行数据（config / db / 日志；不提交 git）
└── tests/             # 单元测试

# 工程脚本在仓库外（开发机工作区级工程台，不随仓库分发）：
#   ../workbench/  → tools/（测试、更新、统计、启动器构建）、experiments/、temp/
```

## 四、关键事实

- **App 机制**：启动时递归扫描 `apps/`；含 `manifest.json` 的目录 = App；按 `app_id` 缓存模块、
  按文件 mtime 热重载；`core.run(params)` 在本地进程内调用（无沙箱）；后台 App 需实现 `teardown()`。
  完整规格见《App 开发指南》。
- **前端挂载**：桌面读取 App 的 `ui/index.html`，经 iframe `srcdoc` 挂载并注入 `<base>`，
  用 postMessage 握手；共享样式由中枢注入（`shared/common/css/` 与 `system/desktop/css/`
  必须一致，有测试守护）。
- **服务即 App**：没有独立的服务类别。常驻端口 / 后台逻辑直接写成 `type: "service"` 的 App
  （示例 `apps/work/hello`），由「后台」面板统一管理。
- **配置**：`data/config/`（config.yaml、score_rules.json、class_datacenter.json、.env）、
  `data/local_config.json`（无边框开关等本机设置）、`data/automation.json`。

## 五、开发约定

- **导入**：统一包绝对导入（`from common.paths import PROJECT_ROOT`），禁止 `sys.path` 技巧
  与相对导入；`apps/` 不得 import `system.*`（有依赖方向测试）。
- **路径**：一律从 `common.paths` 取，禁止散落硬编码；`GYun.core.constants` 只作兼容转发。
- **启动**：统一 `python -m 包.模块`；不直接跑 `.py`（App 的 `core.py` 自测除外）。
- **图标**：一律 SVG 文件，禁止 emoji / Unicode 字符当图标。
- **测试**：改完中枢代码跑 `python ../workbench/tools/run_tests.py`（工程台在仓库外；当前 145 项，全绿才收工）。
- **版本**：`pyproject.toml`（packages 根在 `shared/`），当前 3.0.0。

## 六、常用命令

```bash
pip install -e .                 # 注册 GYun / BYu（首次或环境变化后）
python -m system.main            # 启动中枢
python ../workbench/tools/run_tests.py          # 全量测试（工程台在仓库外）
```
