import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "macro"))
import pages  # noqa: E402

_spec = importlib.util.spec_from_file_location("server_serve_val", ROOT / "server" / "serve.py")
board = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(board)

SAMPLE = {"title": "估值", "updated": "2026-01-02 21:00 UTC", "sections": [
    {"heading": "第一節", "note": "說明 <b>", "head": ["甲", "乙", "來源"],
     "rows": [["一", "<script>", [["官方", "https://example.org/a"], ["本機", "file:///x"]]]]}]}


class ValPage(unittest.TestCase):
    def test_missing_file_gives_none_and_no_tab(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "none.json"
            self.assertIsNone(pages.val_page(missing))
            html = board.shell(missing)
            self.assertNotIn('data-view="val"', html)
            self.assertNotIn("'val'", html)

    def test_renders_sections_escaped_with_https_links_only(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "view.json"
            f.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
            html = pages.val_page(f)
            self.assertIn("<h2>第一節</h2>", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>", html.split("<main>")[1])
            self.assertIn('href="https://example.org/a"', html)
            self.assertNotIn("file:///x", html.replace("本機", ""))
            shell = board.shell(f)
            self.assertIn('data-view="val"', shell)
            self.assertIn('src="val/"', shell)
            self.assertIn("'ai', 'val', 'guide']", shell)

    def test_bad_file_still_renders_a_page(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "view.json"
            f.write_text("{not json", encoding="utf-8")
            self.assertIn("資料暫時未能載入", pages.val_page(f))

    def test_shell_without_view_matches_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(board.shell(Path(d) / "none.json"), (ROOT / "server" / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
