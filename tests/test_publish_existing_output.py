import shutil
import unittest
import uuid
from pathlib import Path

from publish import build_publish_bundle_from_existing_output


class ExistingOutputPublishTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parents[1] / "tests_tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_build_publish_bundle_from_existing_output_allows_missing_source_pdf(self):
        root = self.make_workspace_dir()
        output_dir = root / "legacy"
        (output_dir / "images").mkdir(parents=True)
        (output_dir / "legacy_digitalized.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nDigital legacy\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "legacy_Korean.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nKorean legacy\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage 1\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001_structure.json").write_text(
            '{"article_header":{"title_text":"Legacy Title","author_line":"By Legacy Author"},"footnotes":["Printed in 1918"]}',
            encoding="utf-8",
        )
        (output_dir / "images" / "page_001.png").write_bytes(b"png")
        (output_dir / "legacy_pipeline_state.json").write_text(
            '{"requested_pages":[1],"successful_pages":[1]}',
            encoding="utf-8",
        )

        bundle = build_publish_bundle_from_existing_output(
            output_dir=str(output_dir),
            name="legacy",
        )

        self.assertEqual(bundle["document"]["title"], "Legacy Title")
        self.assertIsNone(bundle["document"]["source_pdf_path"])
        self.assertTrue(all(asset["asset_type"] != "source_pdf" for asset in bundle["assets"]))


if __name__ == "__main__":
    unittest.main()
