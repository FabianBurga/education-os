from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.events.service import enqueue_canonical_event
from app.modules.intelligence.models import IntelligenceSignal
from app.modules.interventions.models import (
    InterventionSuggestion,
    InterventionSuggestionEvidence,
)

_SEVERITY_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

_RULE_ATTENDANCE_ACADEMIC = "M21_ATTENDANCE_ACADEMIC"
_RULE_ACADEMIC_MISSING = "M21_ACADEMIC_MISSING_WORK"
_RULE_ATTENDANCE = "M21_ATTENDANCE_RISK"
_RULE_REPEATED_LATE = "M21_REPEATED_LATE"
_RULE_ACADEMIC = "M21_ACADEMIC_RISK"
_RULE_MISSING_WORK = "M21_MISSING_WORK"

_ENGINE_RULE_KEYS = frozenset(
    {
        _RULE_ATTENDANCE_ACADEMIC,
        _RULE_ACADEMIC_MISSING,
        _RULE_ATTENDANCE,
        _RULE_REPEATED_LATE,
        _RULE_ACADEMIC,
        _RULE_MISSING_WORK,
    }
)


@dataclass(frozen=True)
class SuggestionRefreshResult:
    generated: int
    refreshed: int
    expired: int
    pending: int


@dataclass(frozen=True)
class SuggestionCandidate:
    student_profile_id: UUID
    academic_period_id: UUID | None
    section_id: UUID | None
    rule_key: str
    recommended_intervention_type: str
    severity: str
    sensitivity: str
    title: str
    rationale_summary: str
    evidence_signal_ids: tuple[UUID, ...]


def _require_generate_permission(
    session: Session,
    principal: CurrentPrincipal,
) -> None:
    allowed = session.exec(
        text(
            """
            SELECT 1
            FROM memberships m
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE m.user_id = CAST(:user_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
              AND m.status = 'ACTIVE'
              AND p.key IN (
                  'intervention.suggestion.generate',
                  'intervention.admin'
              )
            LIMIT 1
            """
        ),
        params={
            "user_id": str(principal.user_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Missing required permission: "
                "intervention.suggestion.generate"
            ),
        )


def _severity_max(
    signals: tuple[IntelligenceSignal, ...],
    *,
    floor: str | None = None,
) -> str:
    severity = max(
        (signal.severity for signal in signals),
        key=lambda value: _SEVERITY_RANK[value],
    )
    if floor is not None and _SEVERITY_RANK[severity] < _SEVERITY_RANK[floor]:
        return floor
    return severity


def _shared_section(
    signals: tuple[IntelligenceSignal, ...],
) -> UUID | None:
    values = {signal.section_id for signal in signals}
    if len(values) == 1:
        return next(iter(values))
    return None


def _rationale(signals: tuple[IntelligenceSignal, ...]) -> str:
    ordered = sorted(signals, key=lambda signal: signal.signal_type)
    metrics = "; ".join(
        (
            f"{signal.signal_type}: "
            f"{float(signal.metric_value):.2f} "
            f"(umbral {float(signal.threshold_value):.2f})"
        )
        for signal in ordered
    )
    return f"Regla determinística sustentada en señales abiertas. {metrics}."


def _dedupe_key(
    *,
    rule_key: str,
    student_profile_id: UUID,
    academic_period_id: UUID | None,
) -> str:
    period = str(academic_period_id) if academic_period_id else "none"
    return f"m21e:{rule_key}:{student_profile_id}:{period}"


def _candidate(
    *,
    rule_key: str,
    signals: tuple[IntelligenceSignal, ...],
    recommended_intervention_type: str,
    sensitivity: str,
    title: str,
    severity_floor: str | None = None,
) -> SuggestionCandidate:
    first = signals[0]
    return SuggestionCandidate(
        student_profile_id=first.student_profile_id,
        academic_period_id=first.academic_period_id,
        section_id=_shared_section(signals),
        rule_key=rule_key,
        recommended_intervention_type=recommended_intervention_type,
        severity=_severity_max(signals, floor=severity_floor),
        sensitivity=sensitivity,
        title=title,
        rationale_summary=_rationale(signals),
        evidence_signal_ids=tuple(
            sorted((signal.id for signal in signals), key=str)
        ),
    )


def _build_candidates(
    signals: list[IntelligenceSignal],
) -> list[SuggestionCandidate]:
    grouped: dict[
        tuple[UUID, UUID | None],
        dict[str, IntelligenceSignal],
    ] = {}
    for signal in signals:
        if signal.status != "OPEN":
            continue
        grouped.setdefault(
            (signal.student_profile_id, signal.academic_period_id),
            {},
        )[signal.signal_type] = signal

    candidates: list[SuggestionCandidate] = []

    for bundle in grouped.values():
        consumed: set[str] = set()

        attendance = bundle.get("ATTENDANCE_RISK")
        academic = bundle.get("ACADEMIC_RISK")
        missing = bundle.get("MISSING_WORK")
        late = bundle.get("REPEATED_LATE")

        if attendance is not None and academic is not None:
            candidates.append(
                _candidate(
                    rule_key=_RULE_ATTENDANCE_ACADEMIC,
                    signals=(attendance, academic),
                    recommended_intervention_type="INTEGRATED_SUPPORT",
                    sensitivity="RESTRICTED",
                    title="Revisar riesgo combinado de asistencia y rendimiento",
                    severity_floor="HIGH",
                )
            )
            consumed.update({"ATTENDANCE_RISK", "ACADEMIC_RISK"})

        if (
            academic is not None
            and missing is not None
            and "ACADEMIC_RISK" not in consumed
        ):
            candidates.append(
                _candidate(
                    rule_key=_RULE_ACADEMIC_MISSING,
                    signals=(academic, missing),
                    recommended_intervention_type="ACADEMIC",
                    sensitivity="GENERAL",
                    title="Revisar recuperación académica y trabajos pendientes",
                    severity_floor="HIGH",
                )
            )
            consumed.update({"ACADEMIC_RISK", "MISSING_WORK"})

        if attendance is not None and "ATTENDANCE_RISK" not in consumed:
            candidates.append(
                _candidate(
                    rule_key=_RULE_ATTENDANCE,
                    signals=(attendance,),
                    recommended_intervention_type="ATTENDANCE",
                    sensitivity="GENERAL",
                    title="Revisar riesgo de inasistencia",
                )
            )

        if academic is not None and "ACADEMIC_RISK" not in consumed:
            candidates.append(
                _candidate(
                    rule_key=_RULE_ACADEMIC,
                    signals=(academic,),
                    recommended_intervention_type="ACADEMIC",
                    sensitivity="GENERAL",
                    title="Revisar riesgo académico",
                )
            )

        if missing is not None and "MISSING_WORK" not in consumed:
            candidates.append(
                _candidate(
                    rule_key=_RULE_MISSING_WORK,
                    signals=(missing,),
                    recommended_intervention_type="ACADEMIC",
                    sensitivity="GENERAL",
                    title="Revisar trabajos pendientes reiterados",
                )
            )

        if late is not None:
            candidates.append(
                _candidate(
                    rule_key=_RULE_REPEATED_LATE,
                    signals=(late,),
                    recommended_intervention_type="ATTENDANCE",
                    sensitivity="GENERAL",
                    title="Revisar atrasos reiterados",
                )
            )

    return candidates


def _emit_suggestion_event(
    session: Session,
    principal: CurrentPrincipal,
    suggestion: InterventionSuggestion,
    *,
    event_type: str,
    evidence_signal_ids: tuple[UUID, ...] = (),
) -> None:
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type="intervention_suggestion",
        aggregate_id=suggestion.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(suggestion.student_profile_id),
            "suggestion_id": str(suggestion.id),
            "rule_key": suggestion.rule_key,
            "rule_version": suggestion.rule_version,
            "generation_mode": suggestion.generation_mode,
            "recommended_intervention_type": (
                suggestion.recommended_intervention_type
            ),
            "severity": suggestion.severity,
            "sensitivity": suggestion.sensitivity,
            "status": suggestion.status,
            "evidence_signal_ids": [
                str(signal_id) for signal_id in evidence_signal_ids
            ],
        },
        metadata={
            "deterministic_rule_engine": True,
            "human_authorized": False,
        },
    )


def refresh_intervention_suggestions(
    session: Session,
    principal: CurrentPrincipal,
) -> SuggestionRefreshResult:
    _require_generate_permission(session, principal)

    open_signals = list(
        session.exec(
            select(IntelligenceSignal)
            .where(IntelligenceSignal.status == "OPEN")
            .order_by(
                IntelligenceSignal.student_profile_id,
                IntelligenceSignal.academic_period_id,
                IntelligenceSignal.signal_type,
            )
        ).all()
    )
    candidates = _build_candidates(open_signals)
    now = datetime.now(UTC)

    generated = 0
    refreshed = 0
    expired = 0
    desired_dedupe_keys: set[str] = set()

    for candidate in candidates:
        dedupe_key = _dedupe_key(
            rule_key=candidate.rule_key,
            student_profile_id=candidate.student_profile_id,
            academic_period_id=candidate.academic_period_id,
        )
        desired_dedupe_keys.add(dedupe_key)

        suggestion = session.exec(
            select(InterventionSuggestion).where(
                InterventionSuggestion.dedupe_key == dedupe_key,
                InterventionSuggestion.status == "PENDING",
            )
        ).first()

        if suggestion is None:
            suggestion = InterventionSuggestion(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                student_profile_id=candidate.student_profile_id,
                academic_period_id=candidate.academic_period_id,
                section_id=candidate.section_id,
                rule_key=candidate.rule_key,
                rule_version=1,
                generation_mode="RULE_ENGINE",
                dedupe_key=dedupe_key,
                recommended_intervention_type=(
                    candidate.recommended_intervention_type
                ),
                severity=candidate.severity,
                sensitivity=candidate.sensitivity,
                title=candidate.title,
                rationale_summary=candidate.rationale_summary,
                status="PENDING",
                generated_at=now,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(suggestion)
            session.flush()
            generated += 1
            _emit_suggestion_event(
                session,
                principal,
                suggestion,
                event_type="student.intervention_suggestion.generated",
                evidence_signal_ids=candidate.evidence_signal_ids,
            )
        else:
            suggestion.section_id = candidate.section_id
            suggestion.recommended_intervention_type = (
                candidate.recommended_intervention_type
            )
            suggestion.severity = candidate.severity
            suggestion.sensitivity = candidate.sensitivity
            suggestion.title = candidate.title
            suggestion.rationale_summary = candidate.rationale_summary
            suggestion.last_seen_at = now
            suggestion.updated_at = now
            session.add(suggestion)
            refreshed += 1

        for signal_id in candidate.evidence_signal_ids:
            existing_evidence = session.exec(
                select(InterventionSuggestionEvidence).where(
                    InterventionSuggestionEvidence.suggestion_id
                    == suggestion.id,
                    InterventionSuggestionEvidence.evidence_type
                    == "INTELLIGENCE_SIGNAL",
                    InterventionSuggestionEvidence.evidence_id
                    == signal_id,
                )
            ).first()
            if existing_evidence is None:
                session.add(
                    InterventionSuggestionEvidence(
                        organization_id=principal.organization_id,
                        institution_id=principal.institution_id,
                        suggestion_id=suggestion.id,
                        evidence_type="INTELLIGENCE_SIGNAL",
                        evidence_id=signal_id,
                        created_at=now,
                    )
                )

    pending_engine_suggestions = list(
        session.exec(
            select(InterventionSuggestion).where(
                InterventionSuggestion.status == "PENDING",
                InterventionSuggestion.generation_mode == "RULE_ENGINE",
                InterventionSuggestion.rule_key.in_(_ENGINE_RULE_KEYS),
            )
        ).all()
    )

    for suggestion in pending_engine_suggestions:
        if suggestion.dedupe_key in desired_dedupe_keys:
            continue
        suggestion.status = "EXPIRED"
        suggestion.updated_at = now
        session.add(suggestion)
        expired += 1
        _emit_suggestion_event(
            session,
            principal,
            suggestion,
            event_type="student.intervention_suggestion.expired",
        )

    session.commit()

    pending = len(
        list(
            session.exec(
                select(InterventionSuggestion).where(
                    InterventionSuggestion.status == "PENDING",
                    InterventionSuggestion.generation_mode == "RULE_ENGINE",
                    InterventionSuggestion.rule_key.in_(_ENGINE_RULE_KEYS),
                )
            ).all()
        )
    )

    return SuggestionRefreshResult(
        generated=generated,
        refreshed=refreshed,
        expired=expired,
        pending=pending,
    )
