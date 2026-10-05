"""文件 App - 逻辑入口：浏览与管理 `data/` 下的文件与文件夹。

根目录被**锁死在 `data/`**：所有传入的路径都经 `_resolve()` 解析，
绝对路径 / 盘符 / `..` 越界一律拒绝（返回 ok:false），与《App 接入规范》的安全底线一致。

动作（params = {"action": ..., "payload": {...}}）：

| action   | payload                      | 说明 |
|----------|------------------------------|------|
| `root`   | —                            | 根信息（绝对路径、条目数、占用） |
| `list`   | `{path}`                     | 列目录（文件夹在前，按名称排） |
| `read`   | `{path}`                     | 文本预览（超限只给前一段） |
| `raw`    | `{path}`                     | 二进制预览（返回 data URI，供界面显示图片） |
| `mkdir`  | `{path, name}`               | 在 path 下新建文件夹 |
| `rename` | `{path, newName}`            | 重命名 |
| `delete` | `{paths, confirm}`           | 删除（需 confirm=true） |
| `move`   | `{paths, destDir}`           | 移动到 data/ 下的另一个目录 |
| `newfile`| `{path, name, content}`      | 新建文本文件 |

设计取舍：不做递归删除以外的花活；删除一律要 `confirm`，且**根目录本身不可删**。
"""

import base64
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from common.paths import DATA_DIR
except Exception:  # 极端情况下退回相对定位（apps/work/系统/文件/core.py → 项目根）
    DATA_DIR = Path(__file__).resolve().parents[4] / "data"

ROOT = DATA_DIR

TEXT_PREVIEW_LIMIT = 256 * 1024          # 文本预览上限（字节）
RAW_PREVIEW_LIMIT = 4 * 1024 * 1024      # 图片等原始数据上限

# 视为纯文本的扩展名（无扩展名的常见配置也按文本处理）
TEXT_EXT = {"txt", "md", "json", "yaml", "yml", "ini", "cfg", "conf", "log", "csv", "tsv",
            "py", "js", "ts", "html", "htm", "css", "xml", "env", "bat", "sh", "sql", "toml"}

# 危险区域（可浏览、可读，但删除时额外提醒）
SENSITIVE_DIRS = {"db", "config"}


# ==================== 路径安全 ====================

def _resolve(rel: str = "") -> Optional[Path]:
    """把相对 `data/` 的路径解析成绝对路径；越界 / 非法返回 None。"""
    raw = str(rel or "").replace("\\", "/").strip()
    while raw.startswith("/"):
        raw = raw[1:]
    p = Path(raw)
    if p.is_absolute() or p.drive:
        return None
    try:
        root = ROOT.resolve()
        target = (root / raw).resolve() if raw else root
    except OSError:
        return None
    if target == root or root in target.parents:
        return target
    return None


def _rel(p: Path) -> str:
    """绝对路径 → 相对 data/ 的 posix 路径（根目录为 ""）。"""
    try:
        r = p.resolve().relative_to(ROOT.resolve()).as_posix()
        return "" if r == "." else r
    except Exception:
        return ""


def _is_sensitive(rel: str) -> bool:
    top = rel.split("/", 1)[0]
    return top in SENSITIVE_DIRS


# ==================== 条目信息 ====================

def _entry(p: Path) -> Dict[str, Any]:
    """
    单个条目的展示信息。目录 size 记 -1（避免递归统计拖慢列目录）。
    """
    st = p.stat()
    is_dir = p.is_dir()
    rel = _rel(p)
    return {
        "name": p.name,
        "path": rel,
        "dir": is_dir,
        "size": -1 if is_dir else st.st_size,
        "mtime": int(st.st_mtime),
        "ext": "" if is_dir else p.suffix.lower().lstrip("."),
        "sensitive": _is_sensitive(rel),
    }


def _scan(path: str) -> Dict[str, Any]:
    """列一个目录（文件夹在前、再按名称，忽略大小写）。"""
    d = _resolve(path)
    if d is None:
        return {"ok": False, "error": "路径非法（必须在 data/ 之内）"}
    if not d.exists():
        return {"ok": False, "error": f"路径不存在：{_rel(d) or 'data'}"}
    if not d.is_dir():
        return {"ok": False, "error": "不是文件夹"}
    try:
        entries: List[Dict[str, Any]] = [_entry(c) for c in d.iterdir()]
    except OSError as e:
        return {"ok": False, "error": f"读取失败：{e}"}
    entries.sort(key=lambda e: (not e["dir"], e["name"].casefold()))
    return {
        "ok": True,
        "path": _rel(d),
        "entries": entries,
        "message": f"{len(entries)} 项",
    }


# ==================== 动作 ====================

def _act_root() -> Dict[str, Any]:
    d = _resolve("")
    total = 0
    count = 0
    try:
        for c in d.iterdir():
            count += 1
            if c.is_file():
                try:
                    total += c.stat().st_size
                except OSError:
                    pass
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "path": "",
        "abs": str(d),
        "count": count,
        "size": total,
        "message": f"data（{count} 个顶层条目，约 {_human(total)}）",
    }


def _human(n: int) -> str:
    step = 1024.0
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < step:
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= step
    return f"{v:.1f} PB"


def _act_read(path: str) -> Dict[str, Any]:
    f = _resolve(path)
    if f is None:
        return {"ok": False, "error": "路径非法"}
    if not f.is_file():
        return {"ok": False, "error": "不是文件"}
    size = f.stat().st_size
    ext = f.suffix.lower().lstrip(".")
    if ext not in TEXT_EXT and size > 0:
        return {"ok": False, "error": f"非文本文件（.{ext or '无扩展名'}），大小 {_human(size)}",
                "binary": True, "size": size}
    try:
        data = f.read_bytes()[:TEXT_PREVIEW_LIMIT]
        text = data.decode("utf-8", "replace")
    except OSError as e:
        return {"ok": False, "error": f"读取失败：{e}"}
    truncated = size > TEXT_PREVIEW_LIMIT
    return {
        "ok": True,
        "path": _rel(f),
        "text": text,
        "size": size,
        "truncated": truncated,
        "message": f"{_human(size)}" + ("（仅显示前 256 KB）" if truncated else ""),
    }


def _act_raw(path: str) -> Dict[str, Any]:
    """返回 data URI（图片预览用）。"""
    f = _resolve(path)
    if f is None or not f.is_file():
        return {"ok": False, "error": "文件不存在"}
    size = f.stat().st_size
    if size > RAW_PREVIEW_LIMIT:
        return {"ok": False, "error": f"文件过大，无法预览（{_human(size)}）"}
    mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    try:
        b = f.read_bytes()
    except OSError as e:
        return {"ok": False, "error": f"读取失败：{e}"}
    return {"ok": True, "mime": mime,
            "data_uri": f"data:{mime};base64," + base64.b64encode(b).decode("ascii")}


def _act_mkdir(path: str, name: str) -> Dict[str, Any]:
    d = _resolve(path)
    n = (name or "").strip()
    if d is None or not d.is_dir():
        return {"ok": False, "error": "父目录无效"}
    if not n or any(ch in n for ch in '\\/:*?"<>|'):
        return {"ok": False, "error": '名字非法（不能为空或包含 \\ / : * ? " < > |）'}
    target = d / n
    if target.exists():
        return {"ok": False, "error": f"已存在同名项：{n}"}
    try:
        target.mkdir()
    except OSError as e:
        return {"ok": False, "error": f"创建失败：{e}"}
    return {"ok": True, "path": _rel(target), "message": f"已新建文件夹：{n}"}


def _act_newfile(path: str, name: str, content: str = "") -> Dict[str, Any]:
    d = _resolve(path)
    n = (name or "").strip()
    if d is None or not d.is_dir():
        return {"ok": False, "error": "父目录无效"}
    if not n or any(ch in n for ch in '\\/:*?"<>|'):
        return {"ok": False, "error": "名字非法"}
    target = d / n
    if target.exists():
        return {"ok": False, "error": f"已存在同名项：{n}"}
    try:
        target.write_text(content or "", encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": f"创建失败：{e}"}
    return {"ok": True, "path": _rel(target), "message": f"已新建文件：{n}"}


def _act_rename(path: str, new_name: str) -> Dict[str, Any]:
    src = _resolve(path)
    n = (new_name or "").strip()
    if src is None or not src.exists():
        return {"ok": False, "error": "条目不存在"}
    if src == _resolve(""):
        return {"ok": False, "error": "根目录不能重命名"}
    if not n or any(ch in n for ch in '\\/:*?"<>|'):
        return {"ok": False, "error": "名字非法"}
    dst = src.parent / n
    if dst.exists() and dst != src:
        return {"ok": False, "error": f"已存在同名项：{n}"}
    try:
        src.rename(dst)
    except OSError as e:
        return {"ok": False, "error": f"重命名失败：{e}"}
    return {"ok": True, "path": _rel(dst), "message": f"已重命名为：{n}"}


def _act_delete(paths: List[str], confirm: bool = False) -> Dict[str, Any]:
    if not confirm:
        return {"ok": False, "error": "删除需要确认（confirm=true）"}
    items = [p for p in (paths or []) if str(p).strip()]
    if not items:
        return {"ok": False, "error": "未选择任何条目"}
    root = _resolve("")
    done, failed = [], []
    for rel in items:
        t = _resolve(rel)
        if t is None or not t.exists():
            failed.append(f"{rel}：不存在或路径非法")
            continue
        if t == root:
            failed.append("根目录不能删除")
            continue
        try:
            if t.is_dir():
                shutil.rmtree(t)
            else:
                t.unlink()
            done.append(_rel(t))
        except OSError as e:
            failed.append(f"{rel}：{e}")
    if failed and not done:
        return {"ok": False, "error": "；".join(failed)}
    return {"ok": True, "deleted": done, "failed": failed,
            "message": f"已删除 {len(done)} 项" + (f"，{len(failed)} 项失败" if failed else "")}


def _act_move(paths: List[str], dest_dir: str) -> Dict[str, Any]:
    dst_dir = _resolve(dest_dir)
    if dst_dir is None or not dst_dir.is_dir():
        return {"ok": False, "error": "目标目录无效"}
    items = [p for p in (paths or []) if str(p).strip()]
    if not items:
        return {"ok": False, "error": "未选择任何条目"}
    done, failed = [], []
    for rel in items:
        s = _resolve(rel)
        if s is None or not s.exists():
            failed.append(f"{rel}：不存在")
            continue
        if dst_dir == s or s in dst_dir.parents:
            failed.append(f"{rel}：不能移动到自身或其子目录")
            continue
        t = dst_dir / s.name
        if t.exists():
            failed.append(f"{rel}：目标已存在同名项")
            continue
        try:
            shutil.move(str(s), str(t))
            done.append(_rel(t))
        except OSError as e:
            failed.append(f"{rel}：{e}")
    if failed and not done:
        return {"ok": False, "error": "；".join(failed)}
    return {"ok": True, "moved": done, "failed": failed,
            "message": f"已移动 {len(done)} 项"}


# ==================== 入口 ====================

def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """App 逻辑入口。任何异常都收口为 ok:false，不让界面白屏。"""
    action = (params or {}).get("action") or "list"
    payload = (params or {}).get("payload") or {}

    try:
        if action == "root":
            return _act_root()
        if action == "list":
            return _scan(payload.get("path", ""))
        if action == "read":
            return _act_read(payload.get("path", ""))
        if action == "raw":
            return _act_raw(payload.get("path", ""))
        if action == "mkdir":
            return _act_mkdir(payload.get("path", ""), payload.get("name", ""))
        if action == "newfile":
            return _act_newfile(payload.get("path", ""), payload.get("name", ""),
                                payload.get("content", ""))
        if action == "rename":
            return _act_rename(payload.get("path", ""), payload.get("newName", ""))
        if action == "delete":
            return _act_delete(payload.get("paths") or [], bool(payload.get("confirm")))
        if action == "move":
            return _act_move(payload.get("paths") or [], payload.get("destDir", ""))
        return {"ok": False, "error": f"未知动作：{action}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    import json
    print(json.dumps(run({"action": "root"}), ensure_ascii=False, indent=2))
    print(json.dumps(run({"action": "list", "payload": {"path": ""}}), ensure_ascii=False, indent=2))
