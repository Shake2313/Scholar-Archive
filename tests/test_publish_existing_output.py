import shutil
import unittest
import uuid
from pathlib import Path

from backend.publish import (
    apply_metadata_override,
    build_publish_bundle_from_existing_output,
    delete_metadata_override,
    infer_output_name,
    load_metadata_override,
    save_metadata_override,
    write_metadata_override,
)


class ExistingOutputPublishTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parent / ".tmp"
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

    def test_infer_output_name_uses_report_prefix(self):
        root = self.make_workspace_dir()
        output_dir = root / "ready"
        output_dir.mkdir()
        (output_dir / "sample_quality_report.json").write_text("{}", encoding="utf-8")

        self.assertEqual(infer_output_name(output_dir), "sample")

    def test_save_metadata_override_round_trips_normalized_values(self):
        root = self.make_workspace_dir()
        output_dir = root / "ready"
        output_dir.mkdir()

        save_metadata_override(
            output_dir,
            "sample",
            {
                "title": " Corrected Title ",
                "publication_year": "1918",
                "doi": "",
            },
        )

        self.assertEqual(
            load_metadata_override(output_dir, "sample"),
            {
                "title": "Corrected Title",
                "publication_year": 1918,
            },
        )
        self.assertEqual(
            apply_metadata_override({"author": "Legacy Author"}, {"title": "Corrected Title"}),
            {"author": "Legacy Author", "title": "Corrected Title"},
        )

    def test_write_metadata_override_replaces_existing_values_and_delete_removes_file(self):
        root = self.make_workspace_dir()
        output_dir = root / "ready"
        output_dir.mkdir()

        save_metadata_override(
            output_dir,
            "sample",
            {
                "title": "Corrected Title",
                "author": "Legacy Author",
            },
        )
        write_metadata_override(
            output_dir,
            "sample",
            {
                "title": "Manual Title",
            },
        )

        self.assertEqual(
            load_metadata_override(output_dir, "sample"),
            {"title": "Manual Title"},
        )
        self.assertIsNotNone(delete_metadata_override(output_dir, "sample"))
        self.assertEqual(load_metadata_override(output_dir, "sample"), {})

    def test_build_publish_bundle_from_existing_output_applies_manual_override(self):
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
        save_metadata_override(
            output_dir,
            "legacy",
            {
                "title": "Corrected Legacy Title",
                "author": "Corrected Author",
                "publication_year": 1919,
            },
        )

        bundle = build_publish_bundle_from_existing_output(
            output_dir=str(output_dir),
            name="legacy",
        )

        self.assertEqual(bundle["document"]["title"], "Corrected Legacy Title")
        self.assertEqual(bundle["document"]["author_display"], "Corrected Author")
        self.assertEqual(bundle["document"]["publication_year"], 1919)
        self.assertEqual(bundle["snapshot"]["manual_override"]["title"], "Corrected Legacy Title")

if __name__ == "__main__":
    unittest.main()
