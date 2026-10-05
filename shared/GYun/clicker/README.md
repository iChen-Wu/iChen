# GYun.Clicker 自动化点击录制模块
## 一、模块概述
`GYun.Clicker` 是 iChen 项目**GYun 基础底座**下的桌面自动化工具，包含两大核心能力：
1. **FlowCapture 录制器**：快捷键捕获鼠标点击，支持中途插入自定义业务函数，录制完成自动存入 GYun.Data 数据库；
2. **ClickDriver 执行器**：从数据库读取流程，自动按序执行鼠标操作、延时、自定义函数，预留 OCR/图像识别扩展位；
3. **交互式 CLI**：命令行菜单交互，无需记忆参数，一键录制/运行/查看流程。

### 架构定位
归属 `GYun` 底层基础模块，依赖项目统一数据中枢 `GYun.data`，所有自动化流程**不落地本地 JSON 文件**，全部持久化到 SQLite 数据库，支持标签、全文检索、统一数据维护。

## 二、目录结构
```
src/GYun/clicker/
├── __init__.py          # 包导出入口
├── cli.py               # 交互式命令行工具（推荐使用）
├── driver.py            # 流程执行核心
├── mouse.py             # 底层鼠标操作封装
├── actions.py           # 可在流程中调用的自定义函数库
├── recorder.py          # FlowCapture 录制器实现
├── utils.py             # 数据转换、校验工具
└── visual/              # 视觉识别预留（暂未实现）
    ├── __init__.py
    ├── image_click.py   # 模板图片匹配点击占位
    └── ocr_click.py     # OCR文字识别点击占位
```

## 三、前置依赖
### 1. 安装项目本地包（必须）
项目根目录执行：
```bash
pip install -e .
```
### 2. 安装键鼠录制依赖
```bash
pip install pyautogui pynput pygetwindow
```

## 四、数据存储规范
所有自动化流程统一存储在 GYun.Data，实体固定类型：`auto_click_flow`
| 实体字段 | 映射说明 |
|--------|--------|
| `title` | 流程全局名称（flow_name） |
| `tags` | 标记来源：`flow_capture`（录制生成）/ `manual`（手动创建） |
| `extra.steps` | 标准步骤数组，兼容录制/手动编写格式 |
| `extra.source` | 流程创建来源标识 |

### 标准步骤 type 全集
1. `pixel`：鼠标操作（左键/右键/双击/拖拽/移动/滚轮）
2. `sleep`：固定延时等待
3. `func`：调用 `actions.py` 内自定义函数，支持传参
4. `image` / `ocr`：视觉识别点击（预留占位，暂不开发）

## 五、交互式 CLI 使用（推荐入口）
### 启动命令（项目根目录运行）
```bash
python -m GYun.clicker.cli
```
### 菜单功能说明
```
==================== GYun Clicker 交互工具 ====================
1. 录制新自动化流程
2. 执行已保存流程
3. 查看数据库内全部流程
0. 退出程序
==============================================================
```
### 1. 录制流程（选项1）
1. 输入流程名称，回车开始录制；
2. 录制快捷键：
   - `F1`：记录当前鼠标坐标，生成左键单击步骤；
   - `F2`：记录当前鼠标坐标，生成右键单击步骤；
   - `F3`：插入自定义函数占位步骤，录制结束后填写；
   - `ESC`：停止录制，进入回填交互；
3. 回填逻辑：
   - 依次填写所有 `F3` 插入的函数；
   - 函数名留空直接删除该步骤；
   - 参数支持 JSON 字典，格式错误自动置空；
4. 自动存入数据库，打印流程实体ID。

### 2. 执行流程（选项2）
1. 自动加载数据库全部流程并展示序号；
2. 输入数字选中对应流程，自动逐步骤执行；
3. 控制台实时打印每一步执行日志、异常报错。

### 3. 查看全部流程（选项3）
展示每条流程：名称、实体ID、步骤总数、创建来源，快速管理数据。

## 六、代码直接调用示例
### 1. 代码启动录制
```python
from GYun.clicker import FlowCapture

rec = FlowCapture("打开配置文件流程")
rec.start()
```

### 2. 代码执行流程
```python
from GYun.clicker import ClickDriver

driver = ClickDriver()
driver.run_flow_by_name("打开配置文件流程")
driver.close()
```

## 七、自定义函数扩展（actions.py）
所有 `func` 类型步骤调用的函数统一写在 `actions.py`，新增函数无需修改执行器：
```python
# 示例内置函数
refresh_data_cache(full_scan: bool)   # 刷新GYun数据缓存
switch_window(title_keyword: str)     # 切换指定窗口
print_message(message: str)           # 控制台打印提示
sleep_custom(duration: float)         # 自定义延时
```
流程配置中通过 `func_name` 指定函数，`args` 传入关键字参数。

## 八、开发扩展说明
1. **视觉模块**：`visual/` 目录仅保留空类占位，后续开发 OCR/图片匹配仅填充该目录，不改动现有执行、录制逻辑；
2. **格式兼容**：录制生成的步骤结构与手动编写流程完全统一，可通过前端/数据库接口编辑修改；
3. **无本地文件**：移除传统 JSON 配置文件，所有流程统一由 GYun.Data 管理，复用数据库备份、检索、标签能力；
4. **错误处理**：鼠标操作支持重试，步骤非法自动跳过，单步失败不中断整条流程。

## 九、常见问题
1. `ModuleNotFoundError: No module named 'GYun.clicker'`
   解决方案：项目根目录执行 `pip install -e .` 本地安装包。
2. 录制快捷键无响应
   Windows：使用管理员终端运行；Mac/Linux：授予键鼠监听权限。
3. 执行 image/ocr 步骤报错
   视觉模块暂未开发，如需使用需后续填充 visual 目录代码。
4. 找不到目标流程
   名称模糊匹配，查看菜单3获取完整流程名称后再执行。