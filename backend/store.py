from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import os
import sqlite3

from .schemas import CATALOG, PipelineError, version

REASONS = {"helpful", "wrong_passage", "unsupported_answer", "wrong_timestamp", "incomplete_answer", "slow_response"}


def redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, dict):
        return {k: redact(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, secrets) for v in value]
    return value


class Store:
    def __init__(self, path=".vidsage/pilot.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS traces (request_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (request_id TEXT PRIMARY KEY REFERENCES traces ON DELETE CASCADE,
                    rating TEXT NOT NULL, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS examples (id TEXT PRIMARY KEY, request_id TEXT REFERENCES traces ON DELETE SET NULL,
                    session_id TEXT, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS selections (id INTEGER PRIMARY KEY, name TEXT NOT NULL, report_id TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS datasets (path TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, attempts INTEGER NOT NULL, reserved REAL NOT NULL);
            ''')
        os.chmod(self.path, 0o600)
        self.purge()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                db.execute("PRAGMA foreign_keys = ON")
                db.execute("PRAGMA secure_delete = ON")
                yield db
        finally:
            db.close()

    def purge(self, now=None):
        cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=30)).isoformat()
        with self.connect() as db:
            db.execute("DELETE FROM traces WHERE created_at < ?", (cutoff,))

    def save_trace(self, trace, secrets=()):
        payload = redact(asdict(trace), secrets)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO traces VALUES (?, ?, ?, ?)",
                       (trace.request_id, trace.session_id, trace.created_at, json.dumps(payload)))
            owner = db.execute("SELECT session_id FROM traces WHERE request_id=?", (trace.request_id,)).fetchone()[0]
            if owner != trace.session_id:
                raise PipelineError("request_conflict", "This retained request ID belongs to another session.")

    def record_feedback(self, event):
        self.purge()
        if not event.consent:
            raise PipelineError("consent_required", "Opt in to local feedback retention first.")
        if event.rating not in ("helpful", "unhelpful") or event.reason not in REASONS:
            raise PipelineError("invalid_feedback", "Choose a supported feedback rating and reason.")
        with self.connect() as db:
            row = db.execute("SELECT 1 FROM traces WHERE request_id=? AND session_id=?", (event.request_id, event.session_id)).fetchone()
            if row is None:
                raise PipelineError("unknown_run", "Feedback must refer to your retained answer.")
            db.execute("INSERT INTO feedback VALUES (?, ?, ?) ON CONFLICT(request_id) DO UPDATE SET rating=excluded.rating, reason=excluded.reason",
                       (event.request_id, event.rating, event.reason))

    def approve_example(self, request_id, example, reviewer, snapshot):
        from .evaluation import validate_example
        if not reviewer.strip():
            raise ValueError("Name the human reviewer.")
        with self.connect() as db:
            row = db.execute("SELECT session_id, payload FROM traces WHERE request_id=?", (request_id,)).fetchone()
            feedback = db.execute("SELECT rating, reason FROM feedback WHERE request_id=?", (request_id,)).fetchone()
            if row is None or feedback is None:
                raise ValueError("Review a retained run with feedback before approving it.")
            trace = json.loads(row[1])
            if example["source_version"] != trace["stages"]["source_version"] or example["question"] != trace["stages"]["question"]:
                raise ValueError("The example must match the reviewed question and frozen source.")
            example = {**example, "reviewer": reviewer, "reviewed": True,
                       "provenance": {"request_id": request_id, "session_id": row[0], "rating": feedback[0], "reason": feedback[1]}}
            validate_example(example, snapshot)
            identifier = version(example)
            db.execute("INSERT OR IGNORE INTO examples VALUES (?, ?, ?, ?)",
                       (identifier, request_id, row[0], json.dumps(example)))
            return identifier

    def export_examples(self):
        path = self.path.parent / "datasets" / "approved.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM examples ORDER BY id").fetchall()
        Path(path).write_text("".join(row[0] + "\n" for row in rows))

    def delete_session(self, session_id):
        with self.connect() as db:
            # Approved examples outlive trace expiry, but never an explicit data deletion.
            db.execute("DELETE FROM examples WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM traces WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM experiments")
        with self.connect() as db:
            db.execute("VACUUM")
        self.export_examples()
        with self.connect() as db:
            paths = db.execute("SELECT path FROM datasets").fetchall()
        for (name,) in paths:
            path = Path(name)
            if path.exists():
                rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                kept = [row for row in rows if row.get("provenance", {}).get("session_id") != session_id]
                if len(kept) != len(rows):
                    temporary = path.with_suffix(path.suffix + ".tmp")
                    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept))
                    temporary.replace(path)

    def register_dataset(self, path):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO datasets VALUES (?)", (str(Path(path).resolve()),))

    def review_queue(self):
        self.purge()
        with self.connect() as db:
            rows = db.execute("SELECT t.payload, f.rating, f.reason FROM traces t JOIN feedback f USING(request_id) WHERE f.rating='unhelpful' ORDER BY t.created_at").fetchall()
        return [{"trace": json.loads(payload), "rating": rating, "reason": reason} for payload, rating, reason in rows]

    def reserve(self, amount, daily_limit=5, attempt_limit=100):
        if amount < 0 or not amount <= daily_limit <= 5 or attempt_limit < 1:
            raise ValueError("Invalid spend or request limit.")
        today = datetime.now(timezone.utc).date().isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO quota VALUES (?, 0, 0)", (today,))
            attempts, reserved = db.execute("SELECT attempts, reserved FROM quota WHERE day=?", (today,)).fetchone()
            if attempts >= attempt_limit or reserved + amount > daily_limit + 1e-12:
                raise PipelineError("request_limit", "The server's daily request or spend limit is reached.")
            db.execute("UPDATE quota SET attempts=attempts+1, reserved=reserved+? WHERE day=?", (amount, today))

    def save_report(self, report):
        with self.connect() as db:
            db.execute("INSERT INTO experiments VALUES (?, ?)", (report["id"], json.dumps(report)))

    def selected(self):
        with self.connect() as db:
            row = db.execute("SELECT name FROM selections ORDER BY id DESC LIMIT 1").fetchone()
        return CATALOG[row[0] if row else "baseline"]

    def select(self, name, report_id):
        if name not in CATALOG:
            raise ValueError("Unknown allowlisted configuration.")
        with self.connect() as db:
            row = db.execute("SELECT payload FROM experiments WHERE id=?", (report_id,)).fetchone()
            report = json.loads(row[0]) if row else {}
            if not report.get("complete") or not report.get("recommendation") or report.get("candidate") != name or report.get("phase") != "heldout" or report.get("mode") != "system" or not report.get("human_reviewed") or not report.get("release_dataset_verified"):
                raise ValueError("Selection requires a complete, passing held-out system comparison.")
            db.execute("INSERT INTO selections(name, report_id, created_at) VALUES (?, ?, ?)",
                       (name, report_id, datetime.now(timezone.utc).isoformat()))

    def rollback(self):
        with self.connect() as db:
            rows = db.execute("SELECT name FROM selections ORDER BY id DESC LIMIT 2").fetchall()
            name = rows[1][0] if len(rows) > 1 else "baseline"
            db.execute("INSERT INTO selections(name, created_at) VALUES (?, ?)", (name, datetime.now(timezone.utc).isoformat()))
        return CATALOG[name]

    def report(self, report_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM experiments WHERE id=?", (report_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown comparison report.")
        return json.loads(row[0])

    def review_report(self, report_id, reviewer):
        if not reviewer.strip():
            raise ValueError("Name the human reviewer.")
        report = self.report(report_id)
        if not report.get("complete"):
            raise ValueError("An incomplete comparison cannot be approved.")
        report.update(human_reviewed=True, reviewer=reviewer)
        with self.connect() as db:
            db.execute("UPDATE experiments SET payload=? WHERE id=?", (json.dumps(report), report_id))
        return report

    def is_reviewed_failure(self, example):
        with self.connect() as db:
            row = db.execute("SELECT 1 FROM examples WHERE id=?", (version(example),)).fetchone()
        return bool(row and example.get("provenance", {}).get("rating") == "unhelpful")
