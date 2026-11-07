"""Reference domain model for student-verified deadline changes.

Demonstration only: in-memory, deterministic, no live LMS or student data.
External authority verification must occur outside this model.
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class DomainError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class Status(str, Enum):
    DETECTED = 'DETECTED'
    PENDING_REVIEW = 'PENDING_REVIEW'
    INVALID = 'INVALID'
    REJECTED = 'REJECTED'
    CONFIRMED = 'CONFIRMED'
    APPLIED = 'APPLIED'


class Decision(str, Enum):
    CONFIRM = 'CONFIRM'
    REJECT = 'REJECT'


def parse_deadline(iso_datetime: str, zone_name: str) -> datetime:
    """Verify aware ISO-8601 timestamp and its IANA time-zone offset."""
    try:
        dt = datetime.fromisoformat(iso_datetime)
        zone = ZoneInfo(zone_name)
    except (ValueError, TypeError, ZoneInfoNotFoundError, KeyError) as exc:
        raise DomainError('INVALID_DATETIME', 'Invalid ISO timestamp or IANA time zone') from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise DomainError('NAIVE_DATETIME', 'Deadline must contain a UTC offset')
    if dt.astimezone(zone).utcoffset() != dt.utcoffset():
        raise DomainError('OFFSET_MISMATCH', 'UTC offset disagrees with named zone')
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class DeadlineValue:
    local_iso: str
    zone_name: str

    def utc(self) -> datetime:
        return parse_deadline(self.local_iso, self.zone_name)


@dataclass(frozen=True)
class Assignment:
    assignment_id: str
    course_id: str
    student_id: str
    title: str
    deadline: DeadlineValue
    version: int = 1


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    assignment_id: str
    source_kind: str
    source_ref: str
    content_sha256: str
    authority_verified: bool
    # verified is an independently established trust property, never extracted from content


@dataclass(frozen=True)
class ChangeCandidate:
    candidate_id: str
    assignment_id: str
    source_id: str
    proposed_deadline: DeadlineValue
    base_version: int
    status: Status = Status.DETECTED


@dataclass(frozen=True)
class HistoryEntry:
    assignment_id: str
    old_deadline: DeadlineValue
    new_deadline: DeadlineValue
    old_version: int
    new_version: int
    candidate_id: str
    source_id: str
    reviewer_id: str


@dataclass(frozen=True)
class DomainEvent:
    kind: str
    subject_id: str
    detail: str


@dataclass
class DeadlineStore:
    assignments: dict[str, Assignment] = field(default_factory=dict)
    sources: dict[str, EvidenceSource] = field(default_factory=dict)
    candidates: dict[str, ChangeCandidate] = field(default_factory=dict)
    history: list[HistoryEntry] = field(default_factory=list)
    events: list[DomainEvent] = field(default_factory=list)

    def add_assignment(self, assignment: Assignment) -> None:
        if not all([assignment.assignment_id, assignment.course_id,
                    assignment.student_id, assignment.title.strip()]):
            raise DomainError('MISSING_FIELD', 'Required assignment field is empty')
        assignment.deadline.utc()
        if assignment.version != 1 or assignment.assignment_id in self.assignments:
            raise DomainError('ASSIGNMENT_CONFLICT', 'New assignment must start at version 1 and be unique')
        self.assignments[assignment.assignment_id] = assignment

    def add_source(self, source: EvidenceSource) -> None:
        if source.assignment_id not in self.assignments:
            raise DomainError('UNKNOWN_ASSIGNMENT', 'Evidence must reference an existing assignment')
        if not source.source_id or not source.source_ref or not source.source_kind:
            raise DomainError('MISSING_PROVENANCE', 'Source must have identity, kind, and reference')
        if len(source.content_sha256) != 64 or any(c not in '0123456789abcdef' for c in source.content_sha256):
            raise DomainError('INVALID_HASH', 'Source SHA256 must be lowercase 64-digit hex')
        if source.source_id in self.sources:
            raise DomainError('DUPLICATE_SOURCE', 'Source already exists')
        self.sources[source.source_id] = source

    def propose(self, candidate: ChangeCandidate) -> Status:
        if candidate.candidate_id in self.candidates:
            raise DomainError('DUPLICATE_CANDIDATE', 'Candidate ID already exists')
        if not candidate.candidate_id or not candidate.assignment_id or not candidate.source_id:
            raise DomainError('MISSING_FIELD', 'Candidate ID, assignment and source are required')
        assignment = self.assignments.get(candidate.assignment_id)
        source = self.sources.get(candidate.source_id)
        if assignment is None or source is None or source.assignment_id != candidate.assignment_id:
            raise DomainError('INVALID_LINK', 'Candidate must link to known matching assignment and source')
        if candidate.status is not Status.DETECTED:
            raise DomainError('ILLEGAL_STATE', 'Candidate must be registered in DETECTED state')
        candidate.proposed_deadline.utc()
        if candidate.proposed_deadline.utc() == assignment.deadline.utc():
            self.candidates[candidate.candidate_id] = replace(candidate, status=Status.INVALID)
            self.events.append(DomainEvent('CandidateInvalid', candidate.candidate_id, 'NO_CHANGE'))
            return Status.INVALID
        self.candidates[candidate.candidate_id] = replace(candidate, status=Status.PENDING_REVIEW)
        self.events.append(DomainEvent('CandidatePendingReview', candidate.candidate_id, 'Source recorded'))
        return Status.PENDING_REVIEW

    def review(self, candidate_id: str, reviewer_id: str, decision: Decision) -> Status:
        candidate = self.candidates.get(candidate_id)
        if candidate is None:
            raise DomainError('UNKNOWN_CANDIDATE', 'Candidate ID not found')
        assignment = self.assignments[candidate.assignment_id]
        if reviewer_id != assignment.student_id:
            raise DomainError('ACTOR_NOT_OWNER', 'Only the owning student may review')
        if not isinstance(decision, Decision):
            raise DomainError('INVALID_DECISION', 'Decision must be CONFIRM or REJECT')
        if candidate.status is Status.APPLIED and decision is Decision.CONFIRM:
            return Status.APPLIED  # safe retry; no second update/event
        if candidate.status is not Status.PENDING_REVIEW:
            raise DomainError('ILLEGAL_STATE', 'Only pending candidates may be reviewed')
        if decision is Decision.REJECT:
            self.candidates[candidate_id] = replace(candidate, status=Status.REJECTED)
            self.events.append(DomainEvent('CandidateRejected', candidate_id, reviewer_id))
            return Status.REJECTED
        source = self.sources[candidate.source_id]
        if not source.authority_verified or source.source_kind not in {'OFFICIAL_LMS', 'INSTRUCTOR_EMAIL'}:
            raise DomainError('SOURCE_NOT_AUTHORIZED', 'Verified official provenance required to apply')
        if candidate.base_version != assignment.version:
            raise DomainError('VERSION_CONFLICT', 'Assignment changed; candidate must be reconsidered')
        if candidate.proposed_deadline.utc() == assignment.deadline.utc():
            raise DomainError('NO_CHANGE', 'Proposed deadline equals current deadline')
        # Atomic in-memory reference transition: confirmed -> applied plus versioned history.
        self.candidates[candidate_id] = replace(candidate, status=Status.CONFIRMED)
        updated = replace(assignment, deadline=candidate.proposed_deadline, version=assignment.version + 1)
        entry = HistoryEntry(assignment.assignment_id, assignment.deadline,
                             updated.deadline, assignment.version, updated.version,
                             candidate_id, source.source_id, reviewer_id)
        self.assignments[assignment.assignment_id] = updated
        self.history.append(entry)
        self.candidates[candidate_id] = replace(candidate, status=Status.APPLIED)
        self.events.append(DomainEvent('DeadlineChangeApplied', candidate_id, f'v{updated.version}'))
        return Status.APPLIED
