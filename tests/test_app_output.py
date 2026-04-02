import json
import shutil
import unittest
import uuid
from pathlib import Path

from backend.app_output import (
    find_pipeline_state,
    load_manual_metadata_override,
    read_metadata_report,
    read_rights_metadata,
)
from backend.publish import write_metadata_override


class AppOutputTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parent / ".tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_load_manual_metadata_override_uses_inferred_output_name(self):
        tmpdir = self.make_workspace_dir()
        (tmpdir / "demo_metadata.json").write_text("{}", encoding="utf-8")
        write_metadata_override(tmpdir, "demo", {"author": "Manual Author"})

        output_name, override = load_manual_metadata_override(tmpdir)

        self.assertEqual(output_name, "demo")
        self.assertEqual(override["author"], "Manual Author")

    def test_read_rights_metadata_prefers_override_then_report(self):
        tmpdir = self.make_workspace_dir()
        (tmpdir / "demo_metadata.json").write_text(
            json.dumps(
                {
                    "effective_metadata": {
                        "author": "Reported Author",
                        "publication_year": 1918,
                        "death_year": None,
                    },
                    "rights_metadata": {
                        "author": "Rights Author",
                        "publication_year": 1917,
                        "death_year": None,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        write_metadata_override(
            tmpdir,
            "demo",
            {"author": "Manual Author", "death_year": 1935},
        )

        metadata = read_rights_metadata(tmpdir)

        self.assertEqual(metadata["author"], "Manual Author")
        self.assertEqual(metadata["publication_year"], "1917")
        self.assertEqual(metadata["death_year"], "1935")

    def test_read_rights_metadata_falls_back_to_rights_check_and_state(self):
        tmpdir = self.make_workspace_dir()
        (tmpdir / "demo_rights_check.json").write_text(
            json.dumps({"publication_year": 1750}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (tmpdir / "demo_pipeline_state.json").write_text(
            json.dumps(
                {
                    "author": "Pipeline Author",
                    "death_year": 1935,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        metadata = read_rights_metadata(tmpdir)
        state = find_pipeline_state(tmpdir)

        self.assertEqual(metadata["author"], "Pipeline Author")
        self.assertEqual(metadata["publication_year"], "1750")
        self.assertEqual(metadata["death_year"], "1935")
        self.assertEqual(state["author"], "Pipeline Author")

    def test_read_metadata_report_returns_none_when_missing(self):
        tmpdir = self.make_workspace_dir()
        self.assertIsNone(read_metadata_report(tmpdir))


if __name__ == "__main__":
    unittest.main()
