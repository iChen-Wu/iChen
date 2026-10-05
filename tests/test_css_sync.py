"""一致性保障：shared/common/css 与 system/desktop/css 的运行副本必须一致。

背景（《App 接入规范》第六节）：
- 唯一来源 = `shared/common/css/`（App 样式注入从这里读）
- 运行副本 = `system/desktop/css/`（index.html 以 file:// 打开时跨目录引用不可靠，故保留一份）

本测试失败 = 改了其中一份而忘了另一份。修法：
    把 shared/common/css/<name> 覆盖到 system/desktop/css/<name>（或反向），再重跑测试。
"""
import unittest
from pathlib import Path

try:
    from GYun.core.constants import PROJECT_ROOT
except Exception:  # GYun 未安装时退回项目根（shell 的上级）
    PROJECT_ROOT = Path(__file__).resolve().parents[1]

NAMES = ("tokens.css", "components.css")
SHARED = PROJECT_ROOT / "shared" / "common" / "css"
COPIES = PROJECT_ROOT / "system" / "desktop" / "css"


def _normalized(path: Path) -> str:
    """读文本并归一换行（CRLF/LF 不算差异）。"""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


class CssCopySyncTest(unittest.TestCase):

    def test_shared_css_exists(self):
        for name in NAMES:
            self.assertTrue((SHARED / name).is_file(), f"缺少唯一来源 {SHARED / name}")

    def test_shell_copy_matches_shared(self):
        for name in NAMES:
            src, copy = SHARED / name, COPIES / name
            self.assertTrue(copy.is_file(),
                            f"缺少运行副本 {copy}（应从 shared/css 复制一份到 shell/css）")
            self.assertEqual(
                _normalized(src), _normalized(copy),
                f"{name} 两份不一致：shared/css 是唯一来源，"
                f"请把 {src} 覆盖到 {copy}（或反向同步）",
            )


if __name__ == "__main__":
    unittest.main()
