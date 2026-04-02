import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path


class PublishSmokeTests(unittest.TestCase):
    def make_workspace_dir(self):
        root = Path(__file__).resolve().parent / ".tmp"
        root.mkdir(exist_ok=True)
        path = root / f"case_{uuid.uuid4().hex}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def python_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        return env

    def build_publishable_output(
        self,
        output_dir: Path,
        *,
        name: str,
        title: str,
        author: str,
        publication_year: int = 1918,
        include_quality_report: bool = True,
    ) -> None:
        (output_dir / "images").mkdir(parents=True)
        (output_dir / f"{name}_digitalized.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nDigital legacy\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / f"{name}_Korean.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nKorean legacy\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nPage 1\n\\end{document}\n",
            encoding="utf-8",
        )
        (output_dir / "page_001_structure.json").write_text(
            json.dumps(
                {
                    "article_header": {
                        "title_text": title,
                        "author_line": f"By {author}",
                    },
                    "footnotes": [f"Printed in {publication_year}"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (output_dir / "images" / "page_001.png").write_bytes(b"png")
        (output_dir / f"{name}_pipeline_state.json").write_text(
            json.dumps({"requested_pages": [1], "successful_pages": [1]}, ensure_ascii=False),
            encoding="utf-8",
        )
        if include_quality_report:
            (output_dir / f"{name}_quality_report.json").write_text(
                json.dumps(
                    {
                        "paper_name": title,
                        "total_pages": 1,
                        "transcription": {
                            "successful_pages": 1,
                            "failed_pages": [],
                            "partial_output": False,
                        },
                        "digitalized_pdf": {"compiled": True},
                        "korean_pdf": {"compiled": True},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    def test_publish_cli_output_dir_dry_run_smoke(self):
        root = self.make_workspace_dir()
        output_dir = root / "legacy"
        self.build_publishable_output(
            output_dir,
            name="legacy",
            title="Legacy Title",
            author="Legacy Author",
            include_quality_report=False,
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.publish",
                "--output-dir",
                str(output_dir),
                "--name",
                "legacy",
                "--dry-run",
                "--slug-conflict",
                "skip",
            ],
            cwd=self.repo_root(),
            env=self.python_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("Status: dry_run", result.stdout)
        report_path = output_dir / "legacy_publish_report.json"
        saved_report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_report["status"], "dry_run")
        self.assertEqual(saved_report["slug_conflict_policy"], "skip")
        self.assertEqual(saved_report["slug"], "legacy-title")

    def test_publish_cli_output_root_dry_run_smoke(self):
        root = self.make_workspace_dir()
        ready = root / "ready_output"
        self.build_publishable_output(
            ready,
            name="ready",
            title="Ready Paper",
            author="Archive Author",
            include_quality_report=True,
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.publish",
                "--output-root",
                str(root),
                "--dry-run",
                "--slug-conflict",
                "skip",
            ],
            cwd=self.repo_root(),
            env=self.python_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("Queued: 1", result.stdout)
        self.assertIn("DRY_RUN ready_output (ready-paper): ok", result.stdout)
        report_path = ready / "ready_publish_report.json"
        saved_report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_report["status"], "dry_run")
        self.assertEqual(saved_report["slug"], "ready-paper")


if __name__ == "__main__":
    unittest.main()
