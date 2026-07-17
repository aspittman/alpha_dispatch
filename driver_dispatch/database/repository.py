from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from driver_dispatch.models import DrivingSession, Event, ScoredOpportunity


class Repository:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")

    def migrate(self) -> None:
        migrations = Path(__file__).parent / "migrations"
        for migration in sorted(migrations.glob("*.sql")):
            version = migration.stem
            exists = self.connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
            ).fetchone() if self._has_migrations_table() else None
            if not exists:
                self.connection.executescript(migration.read_text(encoding="utf-8"))
                self.connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations VALUES (?, ?)",
                    (version, datetime.now(timezone.utc).isoformat()),
                )
                self.connection.commit()

    def _has_migrations_table(self) -> bool:
        return bool(self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone())

    def save_events(self, events: Iterable[Event]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for event in events:
            event.id = event.id or str(uuid.uuid4())
            event.date_first_seen = event.date_first_seen or datetime.now(timezone.utc)
            event.date_last_updated = datetime.now(timezone.utc)
            payload = event.model_dump_json()
            self.connection.execute(
                """INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET source=excluded.source, source_event_id=excluded.source_event_id,
                name=excluded.name, start_datetime=excluded.start_datetime, city=excluded.city,
                status=excluded.status, payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
                (event.id, event.source, event.source_event_id, event.name,
                 event.start_datetime.isoformat() if event.start_datetime else None,
                 event.city, event.status, payload, event.date_first_seen.isoformat(), now),
            )
            for source in event.source_attributions or [event.source]:
                ids = event.source_event_ids.get(source) or ([event.source_event_id] if source == event.source and event.source_event_id else [])
                for source_id in ids:
                    self.connection.execute("INSERT OR IGNORE INTO event_sources VALUES (?, ?, ?)", (event.id, source, source_id))
            self.connection.execute(
                """INSERT INTO event_normalization_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET normalized_at=excluded.normalized_at,
                source_names_json=excluded.source_names_json, source_event_ids_json=excluded.source_event_ids_json,
                source_urls_json=excluded.source_urls_json, conflicting_fields_json=excluded.conflicting_fields_json,
                selected_values_json=excluded.selected_values_json, selection_reasons_json=excluded.selection_reasons_json""",
                (event.id, (event.normalized_at or datetime.now(timezone.utc)).isoformat(), json.dumps(event.source_attributions), json.dumps(event.source_event_ids), json.dumps(event.source_urls), json.dumps(event.conflicting_fields, default=str), json.dumps(event.selected_values, default=str), json.dumps(event.selection_reasons)),
            )
        self.connection.commit()

    def events_between(self, start: datetime, end: datetime) -> list[Event]:
        rows = self.connection.execute(
            "SELECT payload_json FROM events WHERE start_datetime >= ? AND start_datetime < ? ORDER BY start_datetime",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [Event.model_validate_json(row[0]) for row in rows]

    def record_error(self, source: str, message: str, details: dict | None = None) -> None:
        self.connection.execute("INSERT INTO source_errors(source, occurred_at, message, details_json) VALUES (?, ?, ?, ?)",
                                (source, datetime.now(timezone.utc).isoformat(), message, json.dumps(details or {})))
        self.connection.commit()

    def recent_errors(self, since: datetime) -> list[dict]:
        rows = self.connection.execute("SELECT source, occurred_at, message FROM source_errors WHERE occurred_at >= ?", (since.isoformat(),)).fetchall()
        return [dict(row) for row in rows]

    def save_session(self, session: DrivingSession) -> int:
        cursor = self.connection.execute("INSERT INTO driving_sessions(session_date, payload_json, created_at) VALUES (?, ?, ?)",
                                         (session.date.isoformat(), session.model_dump_json(), datetime.now(timezone.utc).isoformat()))
        self.connection.commit()
        return int(cursor.lastrowid)

    def save_report(self, week_start: date, html_path: Path, text_path: Path, opportunities: list[ScoredOpportunity]) -> None:
        payload = json.dumps([o.model_dump(mode="json") for o in opportunities])
        cursor = self.connection.execute("INSERT INTO weekly_reports(week_start, created_at, html_path, text_path, payload_json) VALUES (?, ?, ?, ?, ?)",
                                         (week_start.isoformat(), datetime.now(timezone.utc).isoformat(), str(html_path), str(text_path), payload))
        for item in opportunities:
            self.connection.execute("INSERT INTO recommendations(report_id, event_id, opportunity_score, confidence_score, payload_json, scoring_version) VALUES (?, ?, ?, ?, ?, ?)",
                                    (cursor.lastrowid, item.event.id, item.opportunity_score, item.confidence_score, item.model_dump_json(), "v1-rules"))
        self.connection.commit()

    def save_traffic_run(self, result: dict) -> int:
        payload = json.dumps(result, default=lambda value: value.model_dump(mode="json") if hasattr(value, "model_dump") else value.isoformat())
        cursor = self.connection.execute("INSERT INTO traffic_check_runs(run_mode, origin_name, captured_at, payload_json) VALUES (?, ?, ?, ?)", (result["mode"], result["origin_name"], result["generated_at"].isoformat(), payload))
        run_id = cursor.lastrowid
        for item in result["recommendations"]:
            data = item.model_dump(mode="json")
            self.connection.execute("INSERT INTO zone_recommendations(run_id, zone, classification, payload_json) VALUES (?, ?, ?, ?)", (run_id, item.zone, item.classification, json.dumps(data)))
            if item.route: self.connection.execute("INSERT INTO route_snapshots(run_id, zone, captured_at, payload_json) VALUES (?, ?, ?, ?)", (run_id, item.zone, result["generated_at"].isoformat(), item.route.model_dump_json()))
        for incident in result["incidents"]:
            self.connection.execute("INSERT INTO traffic_incidents(source, source_id, last_seen, payload_json) VALUES (?, ?, ?, ?) ON CONFLICT(source, source_id) DO UPDATE SET last_seen=excluded.last_seen, payload_json=excluded.payload_json", (incident.source, incident.source_id, result["generated_at"].isoformat(), incident.model_dump_json()))
        self.connection.commit(); return int(run_id)

    def latest_traffic_run(self, mode: str):
        row = self.connection.execute("SELECT payload_json FROM traffic_check_runs WHERE run_mode=? ORDER BY captured_at DESC LIMIT 1", (mode,)).fetchone()
        return json.loads(row[0]) if row else None
