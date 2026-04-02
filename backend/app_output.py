"""
Helpers for loading pipeline output artifacts into the Streamlit app.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.publish import infer_output_name, load_metadata_override


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_pipeline_state(output_path: Path):
    state_files = sorted(output_path.glob("*_pipeline_state.json"))
    if not state_files:
        return None
    return read_json(state_files[0])


def read_metadata_report(output_path: Path):
    metadata_files = sorted(output_path.glob("*_metadata.json"))
    if not metadata_files:
        return None
    return read_json(metadata_files[0])


def get_output_name(output_path: Path):
    try:
        return infer_output_name(output_path)
    except Exception:
        return None


def load_manual_metadata_override(output_path: Path):
    output_name = get_output_name(output_path)
    if not output_name:
        return None, {}
    return output_name, load_metadata_override(output_path, output_name)


def read_rights_metadata(output_path: Path):
    metadata = {
        "author": "",
        "publication_year": "",
        "death_year": "",
    }
    data = read_metadata_report(output_path)
    if data:
        effective = data.get("effective_metadata", {}) if isinstance(data, dict) else {}
        rights = data.get("rights_metadata", {}) if isinstance(data, dict) else {}
        metadata["author"] = str(
            rights.get("author")
            or effective.get("author")
            or ""
        )
        metadata["publication_year"] = (
            str(
                rights.get("publication_year")
                if rights.get("publication_year") is not None
                else effective.get("publication_year")
            )
            if (
                rights.get("publication_year") is not None
                or effective.get("publication_year") is not None
            )
            else ""
        )
        metadata["death_year"] = (
            str(
                rights.get("death_year")
                if rights.get("death_year") is not None
                else effective.get("death_year")
            )
            if (
                rights.get("death_year") is not None
                or effective.get("death_year") is not None
            )
            else ""
        )
    _output_name, override = load_manual_metadata_override(output_path)
    if override.get("author"):
        metadata["author"] = str(override.get("author"))
    if override.get("publication_year") is not None:
        metadata["publication_year"] = str(override.get("publication_year"))
    if override.get("death_year") is not None:
        metadata["death_year"] = str(override.get("death_year"))
    rights_files = sorted(output_path.glob("*_rights_check.json"))
    if rights_files:
        data = read_json(rights_files[0])
        if not metadata["author"]:
            metadata["author"] = str(data.get("author") or "")
        if not metadata["publication_year"] and data.get("publication_year") is not None:
            metadata["publication_year"] = str(data.get("publication_year"))
        if not metadata["death_year"] and data.get("death_year") is not None:
            metadata["death_year"] = str(data.get("death_year"))
    state = find_pipeline_state(output_path)
    if state:
        if not metadata["author"]:
            metadata["author"] = str(state.get("author") or "")
        if not metadata["publication_year"] and state.get("publication_year") is not None:
            metadata["publication_year"] = str(state.get("publication_year"))
        if not metadata["death_year"] and state.get("death_year") is not None:
            metadata["death_year"] = str(state.get("death_year"))
    return metadata
