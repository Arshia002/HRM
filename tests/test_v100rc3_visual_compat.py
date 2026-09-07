from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from sazmanhr.database import Repository
from sazmanhr.server import ApiServer


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"

EXPECTED_CSP_PARTS = (
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "style-src-attr 'unsafe-inline'",
    "style-src-elem 'self'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
)


class V100Rc3VisualCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        db = Path(cls.temp.name) / "visual-compat.sqlite"
        shutil.copy2(SEED, db)
        cls.repo = Repository(db)
        cls.server = ApiServer(("127.0.0.1", 0), cls.repo, web_root=WEB)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def test_v49_web_csp_allows_dynamic_style_attributes_only(self) -> None:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as response:
            self.assertEqual(response.status, 200)
            csp = response.headers.get("Content-Security-Policy", "")

        for part in EXPECTED_CSP_PARTS:
            self.assertIn(part, csp)

        # v4.9 uses dynamic element.style/style="" for chart geometry and bar heights.
        # Keep JavaScript strict: inline scripts/eval must remain disallowed.
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertNotIn("'unsafe-eval'", csp)

    def test_all_canonical_chart_page_assets_are_present(self) -> None:
        chart_dir = WEB / "assets" / "chart-pages"
        files = sorted(chart_dir.glob("page-*.webp"))
        self.assertEqual(len(files), 54)
        for page in range(1, 55):
            path = chart_dir / f"page-{page}.webp"
            self.assertTrue(path.is_file(), str(path))
            self.assertGreater(path.stat().st_size, 0, str(path))

    def test_canonical_monthly_import_template_is_present(self) -> None:
        template = WEB / "assets" / "templates" / "SazmanHR-Monthly-Import-Template.xlsx"
        self.assertTrue(template.is_file(), str(template))
        self.assertGreater(template.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
