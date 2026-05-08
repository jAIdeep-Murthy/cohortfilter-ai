"""In-memory + JSON file storage. MindsDB-free fallback for hackathon MVP."""

import json
import os
from typing import Optional, List, Dict
from models import RubricConfig, ApplicationResult

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "state")


class Storage:
    def __init__(self):
        self._rubric: Optional[RubricConfig] = None
        self._applications: Dict[str, List[Dict]] = {}  # upload_id -> rows
        self._results: Dict[str, List[Dict]] = {}  # job_id -> scored results
        os.makedirs(DATA_DIR, exist_ok=True)

    # ── Rubric ──────────────────────────────────────────────
    def save_rubric(self, rubric: RubricConfig):
        self._rubric = rubric
        self._write_json("rubric.json", rubric.model_dump())

    def get_rubric(self) -> Optional[RubricConfig]:
        if self._rubric:
            return self._rubric
        data = self._read_json("rubric.json")
        if data:
            self._rubric = RubricConfig(**data)
            return self._rubric
        return None

    # ── Applications (uploaded CSVs) ────────────────────────
    def save_applications(self, upload_id: str, rows: List[Dict]):
        self._applications[upload_id] = rows
        self._write_json(f"upload_{upload_id}.json", rows)

    def get_applications(self, upload_id: str) -> Optional[List[Dict]]:
        if upload_id in self._applications:
            return self._applications[upload_id]
        data = self._read_json(f"upload_{upload_id}.json")
        if data:
            self._applications[upload_id] = data
            return data
        return None

    # ── Scored Results ──────────────────────────────────────
    def save_results(self, upload_id: str, job_id: str, results: List[Dict]):
        self._results[job_id] = results
        self._write_json(f"results_{job_id}.json", results)

    def get_results(self, job_id: str) -> Optional[List[Dict]]:
        if job_id in self._results:
            return self._results[job_id]
        data = self._read_json(f"results_{job_id}.json")
        if data:
            self._results[job_id] = data
            return data
        return None

    # ── Helpers ─────────────────────────────────────────────
    def _write_json(self, filename: str, data):
        path = os.path.join(DATA_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def _read_json(self, filename: str):
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
