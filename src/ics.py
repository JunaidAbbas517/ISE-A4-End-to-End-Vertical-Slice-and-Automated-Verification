"""Export adapter (A3 ADR-001): one confirmed tracked deadline as an iCalendar VTODO.

The export is a read-only copy. Edits made in an external calendar are NOT read back;
per ADR-001 they would be new, unverified input.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.domain import parse_deadline


def escape_text(value: str) -> str:
    """RFC 5545 section 3.3.11 TEXT escaping."""
    return (value.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\n'))


def _utc_stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def assignment_to_ics(assignment: dict, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    due = parse_deadline(assignment['deadline_local_iso'], assignment['deadline_zone'])
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//ISE-A4//Deadline Verification Slice//EN',
        'BEGIN:VTODO',
        f"UID:{assignment['assignment_id']}@ise-a4.invalid",
        f"SEQUENCE:{int(assignment['version']) - 1}",
        f'DTSTAMP:{_utc_stamp(now)}',
        f'DUE:{_utc_stamp(due)}',
        f"SUMMARY:{escape_text(assignment['title'])}",
        'DESCRIPTION:' + escape_text(
            f"Personal tracked deadline v{assignment['version']} "
            f"({assignment['deadline_local_iso']} {assignment['deadline_zone']}). "
            'Not an official university record.'),
        'END:VTODO',
        'END:VCALENDAR',
    ]
    return '\r\n'.join(lines) + '\r\n'
