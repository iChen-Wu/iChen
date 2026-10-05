#!/usr/bin/env python3
"""iChen 交付版启动器（项目根 / 交付版根目录）。

职责**只有三件**，真正的程序在 `system/main.py`：

1. **找 Python**：交付版自带 `runtime/python.exe`（嵌入式）→ 退回系统 Python → 都没有则弹窗；
2. **检查 WebView2**：缺失时用 MessageBox 明确提示（pywebview 在 Windows 上依赖它）；
3. **交给内核**：把 `system/` 放进 sys.path，调用 `system.main.main()`。

首次运行装依赖（交付版自带 pip）：

    runtime\\python.exe -m pip install pywebview

（开发版依赖见 requirements.txt；交付版只需 pywebview 与项目已内联的库。）

打包成 exe（可选，PyInstaller）：

    pyinstaller --onefile --name iChen --console main.py

更新策略：**只换中枢代码**——用工程台 `../workbench/tools/update_production.py --apply`
把 `system/`、`main.py`、`README.md` 同步到正式版；`apps/ shared/ data/ runtime/`
受工具保护永不覆盖（用户 App、业务库、业务数据、自带 Python 各自独立）。

开发版不需要本文件——直接 `python -m system.main` 即可。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SYSTEM_DIR = ROOT / "system"
RUNTIME_PY = ROOT / "runtime" / "python.exe"


def _message_box(text: str, title: str = "iChen") -> None:
    """能弹窗就弹窗，弹不出来就打印（交付场景下用户看不到控制台）。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
    except Exception:
        print(f"[{title}] {text}", file=sys.stderr)


def _has_webview2() -> bool:
    """检查 Microsoft Edge WebView2 Runtime 是否已安装（查注册表）。"""
    if os.name != "nt":
        return True
    try:
        import winreg
    except ImportError:
        return True
    keys = (
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    )
    for hive, sub in keys:
        try:
            with winreg.OpenKey(hive, sub) as k:
                winreg.QueryValueEx(k, "pv")
                return True
        except OSError:
            continue
    return False


def _reexec_with_runtime() -> None:
    """如果当前解释器不是交付版自带的，就用 runtime/python.exe 重启一次。

    注意：**同目录的 `python.exe` 与 `pythonw.exe` 都算自带 runtime**——
    便携启动器用 `pythonw.exe` 无控制台启动，不能因此判定为"外来解释器"
    而再拉起一次 `python.exe`（会多一个进程 + 闪一个控制台窗口）。
    """
    if not RUNTIME_PY.is_file():
        return
    try:
        cur = Path(sys.executable).resolve()
        runtime_dir = RUNTIME_PY.parent.resolve()
        same = cur == RUNTIME_PY.resolve() or (
            cur.parent == runtime_dir
            and cur.name.lower() in ("python.exe", "pythonw.exe")
        )
    except OSError:
        same = False
    if same:
        return
    args = [str(RUNTIME_PY), str(Path(__file__).resolve())] + sys.argv[1:]
    raise SystemExit(subprocess.call(args))


def main() -> int:
    if not SYSTEM_DIR.is_dir():
        _message_box(f"找不到 system 目录：\n{SYSTEM_DIR}\n\n请确认交付包完整。")
        return 1
    if not _has_webview2():
        _message_box("缺少 Microsoft Edge WebView2 Runtime，界面无法启动。\n\n"
                     "请安装后重试：\nhttps://developer.microsoft.com/microsoft-edge/webview2/")
        return 1

    _reexec_with_runtime()      # 有自带 runtime 就切过去（没有则继续用当前解释器）

    for p in (str(ROOT), str(SYSTEM_DIR), str(ROOT / "shared")):
        if p not in sys.path:
            sys.path.insert(0, p)

    try:
        from system.main import main as kernel_main
    except Exception as e:
        _message_box(f"加载 system/main.py 失败：\n{e}")
        return 1
    kernel_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
