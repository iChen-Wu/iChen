"""内核启动脚本的静态与行为检查。

起因（真实缺陷）：`system/main.py` 里 `api._frameless = frameless` 被写在
`frameless = ...` **之前**，运行即 `UnboundLocalError: cannot access local variable`。
本文件用 AST 把这类「函数内先读后写」的问题钉住——它对 `system/` 全量扫描，
因为这类错在 GUI 里一点就崩，而当前环境开不了窗。
"""
import ast
import unittest
from pathlib import Path

import system.main as m

ROOT = Path(__file__).resolve().parents[1]


class ParseFlagsTest(unittest.TestCase):

    def test_defaults(self):
        f = m.parse_flags(["main.py"])
        self.assertFalse(f["debug"])       # 默认关调试
        self.assertFalse(f["frameless"])   # 默认用原生标题栏

    def test_debug(self):
        self.assertTrue(m.parse_flags(["main.py", "--debug"])["debug"])

    def test_frameless(self):
        self.assertTrue(m.parse_flags(["main.py", "--frameless"])["frameless"])

    def test_both(self):
        f = m.parse_flags(["main.py", "--frameless", "--debug"])
        self.assertTrue(f["frameless"])
        self.assertTrue(f["debug"])


class UnboundLocalGuardTest(unittest.TestCase):
    """扫 system/ ：函数内不得「先读某局部名，之后才给它赋值」。"""

    @staticmethod
    def _first_load_store(fn: ast.AST):
        """返回 {名字: [首次 Load 行号, 首次 Store 行号]}（只看该函数自身，不下钻嵌套函数）。"""
        seen = {}

        def walk(node):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue                      # 嵌套函数作用域不同，跳过
                if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Load, ast.Store)):
                    rec = seen.setdefault(child.id, [None, None])
                    idx = 0 if isinstance(child.ctx, ast.Load) else 1
                    if rec[idx] is None:
                        rec[idx] = child.lineno
                walk(child)

        walk(fn)
        return seen

    def test_no_read_before_write_in_system(self):
        problems = []
        for py in sorted((ROOT / "system").rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError as e:
                problems.append(f"{py.relative_to(ROOT)} 语法错误: {e}")
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                # 参数与 global/nonlocal 声明不参与该检查
                params = {a.arg for a in node.args.args + node.args.kwonlyargs}
                if node.args.vararg:
                    params.add(node.args.vararg.arg)
                if node.args.kwarg:
                    params.add(node.args.kwarg.arg)
                declared = set()
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.Global, ast.Nonlocal)):
                        declared.update(sub.names)

                for name, (load_line, store_line) in self._first_load_store(node).items():
                    if name in params or name in declared:
                        continue
                    if load_line is not None and store_line is not None and load_line < store_line:
                        problems.append(
                            f"{py.relative_to(ROOT)}:{load_line} 读取 `{name}` 早于它在 "
                            f"第 {store_line} 行的赋值（会 UnboundLocalError）")
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
