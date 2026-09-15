"""M21-F2 least-privilege Student Timeline projection boundary.

Revision ID: 0024_m21_projection_boundary
Revises: 0023_m21_suggestions
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_m21_projection_boundary"
down_revision: str | None = "0023_m21_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTION_SIGNATURE = (
    "public.m21_student_timeline_source_events("
    "uuid,uuid,bigint,integer)"
)


def upgrade() -> None:
    # The runtime role intentionally cannot read event_ledger.payload_json.
    # Expose only the M21 Timeline payload keys required by the projector,
    # and only to an authenticated tenant-bound admin principal.
    op.execute(
        """
        CREATE FUNCTION public.m21_student_timeline_source_events(
            p_organization_id uuid,
            p_institution_id uuid,
            p_after_position bigint,
            p_limit integer
        )
        RETURNS TABLE (
            id uuid,
            ledger_position bigint,
            organization_id uuid,
            institution_id uuid,
            event_type text,
            event_version integer,
            aggregate_type text,
            aggregate_id uuid,
            actor_user_id uuid,
            correlation_id uuid,
            causation_id uuid,
            payload_json jsonb,
            occurred_at timestamptz,
            recorded_at timestamptz
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
        DECLARE
            v_context_organization_id uuid :=
                NULLIF(
                    pg_catalog.current_setting(
                        'app.organization_id',
                        true
                    ),
                    ''
                )::uuid;
            v_context_institution_id uuid :=
                NULLIF(
                    pg_catalog.current_setting(
                        'app.institution_id',
                        true
                    ),
                    ''
                )::uuid;
            v_context_user_id uuid :=
                NULLIF(
                    pg_catalog.current_setting(
                        'app.user_id',
                        true
                    ),
                    ''
                )::uuid;
            v_after_position bigint :=
                GREATEST(COALESCE(p_after_position, 0), 0);
            v_limit integer :=
                LEAST(GREATEST(COALESCE(p_limit, 1000), 1), 5000);
        BEGIN
            IF session_user <> 'education_app' THEN
                RAISE EXCEPTION
                    'M21 timeline projection source is runtime-only'
                    USING ERRCODE = '42501';
            END IF;

            IF v_context_organization_id IS DISTINCT FROM p_organization_id
               OR v_context_institution_id IS DISTINCT FROM p_institution_id
            THEN
                RAISE EXCEPTION
                    'M21 timeline projection tenant context mismatch'
                    USING ERRCODE = '42501';
            END IF;

            IF v_context_user_id IS NULL THEN
                RAISE EXCEPTION
                    'M21 timeline projection requires an app principal'
                    USING ERRCODE = '42501';
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM public.institutions i
                WHERE i.id = p_institution_id
                  AND i.organization_id = p_organization_id
                  AND i.status = 'ACTIVE'
            ) THEN
                RAISE EXCEPTION
                    'M21 timeline projection tenant is not active'
                    USING ERRCODE = '42501';
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM public.user_accounts ua
                JOIN public.memberships m
                  ON m.user_id = ua.id
                 AND m.institution_id = p_institution_id
                 AND m.status = 'ACTIVE'
                JOIN public.membership_roles mr
                  ON mr.membership_id = m.id
                JOIN public.role_permissions rp
                  ON rp.role_id = mr.role_id
                JOIN public.permissions p
                  ON p.id = rp.permission_id
                WHERE ua.id = v_context_user_id
                  AND ua.is_active = true
                  AND p.key = 'admin.console.access'
            ) THEN
                RAISE EXCEPTION
                    'M21 timeline projection requires admin.console.access'
                    USING ERRCODE = '42501';
            END IF;

            RETURN QUERY
            WITH source_rows AS (
                SELECT
                    l.id,
                    l.position,
                    l.organization_id,
                    l.institution_id,
                    l.event_type::text AS event_type,
                    l.event_version,
                    l.aggregate_type::text AS aggregate_type,
                    l.aggregate_id,
                    l.actor_user_id,
                    l.correlation_id,
                    l.causation_id,
                    l.payload_json AS raw_payload_json,
                    l.occurred_at,
                    l.recorded_at,
                    CASE
                        WHEN l.event_type = 'student.enrollment.created'
                        THEN ARRAY[
                            'student_profile_id',
                            'academic_period_id',
                            'campus_id',
                            'status',
                            'enrolled_on'
                        ]::text[]
                        WHEN l.event_type = 'student.enrollment.status_changed'
                        THEN ARRAY[
                            'student_profile_id',
                            'academic_period_id',
                            'previous_status',
                            'status',
                            'withdrawn_on'
                        ]::text[]
                        WHEN l.event_type IN (
                            'student.attendance.recorded',
                            'student.attendance.updated'
                        )
                        THEN ARRAY[
                            'student_profile_id',
                            'student_section_assignment_id',
                            'class_session_id',
                            'section_id',
                            'attendance_code_id',
                            'minutes_late'
                        ]::text[]
                        WHEN l.event_type IN (
                            'student.grade.recorded',
                            'student.grade.updated'
                        )
                        THEN ARRAY[
                            'student_profile_id',
                            'student_section_assignment_id',
                            'assessment_id',
                            'section_id',
                            'status',
                            'score'
                        ]::text[]
                        WHEN l.event_type = 'student.signal.opened'
                        THEN ARRAY[
                            'student_profile_id',
                            'academic_period_id',
                            'section_id',
                            'signal_type',
                            'severity',
                            'metric_value',
                            'threshold_value',
                            'summary'
                        ]::text[]
                        WHEN l.event_type IN (
                            'student.signal.closed',
                            'student.signal.resolved'
                        )
                        THEN ARRAY[
                            'student_profile_id',
                            'academic_period_id',
                            'section_id',
                            'signal_type',
                            'severity',
                            'closure_type'
                        ]::text[]
                        WHEN l.event_type IN (
                            'student.intervention.opened',
                            'student.intervention.assigned'
                        )
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'intervention_type',
                            'status',
                            'severity',
                            'sensitivity',
                            'origin_type',
                            'assigned_role_code',
                            'assigned_user_id',
                            'academic_period_id',
                            'section_id',
                            'target_at'
                        ]::text[]
                        WHEN l.event_type = 'student.intervention.status_changed'
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'intervention_type',
                            'previous_status',
                            'status',
                            'severity',
                            'sensitivity',
                            'origin_type',
                            'assigned_role_code',
                            'assigned_user_id',
                            'academic_period_id',
                            'section_id',
                            'target_at'
                        ]::text[]
                        WHEN l.event_type = 'student.intervention.cancelled'
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'intervention_type',
                            'previous_status',
                            'status',
                            'severity',
                            'sensitivity',
                            'origin_type',
                            'assigned_role_code',
                            'assigned_user_id',
                            'academic_period_id',
                            'section_id',
                            'target_at',
                            'cancellation_reason_recorded'
                        ]::text[]
                        WHEN l.event_type IN (
                            'student.intervention.resolved',
                            'student.intervention.closed'
                        )
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'intervention_type',
                            'previous_status',
                            'status',
                            'severity',
                            'sensitivity',
                            'origin_type',
                            'assigned_role_code',
                            'assigned_user_id',
                            'academic_period_id',
                            'section_id',
                            'target_at',
                            'outcome_type'
                        ]::text[]
                        WHEN l.event_type = 'student.intervention.reopened'
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'intervention_type',
                            'previous_status',
                            'status',
                            'severity',
                            'sensitivity',
                            'origin_type',
                            'assigned_role_code',
                            'assigned_user_id',
                            'academic_period_id',
                            'section_id',
                            'target_at'
                        ]::text[]
                        WHEN l.event_type IN (
                            'student.intervention.action_created',
                            'student.intervention.action_assigned'
                        )
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'action_id',
                            'action_type',
                            'status',
                            'severity',
                            'sensitivity',
                            'assigned_role_code',
                            'assigned_user_id',
                            'due_at'
                        ]::text[]
                        WHEN l.event_type IN (
                            'student.intervention.action_acknowledged',
                            'student.intervention.action_started',
                            'student.intervention.action_cancelled'
                        )
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'action_id',
                            'action_type',
                            'previous_status',
                            'status',
                            'severity',
                            'sensitivity',
                            'assigned_role_code',
                            'assigned_user_id',
                            'due_at'
                        ]::text[]
                        WHEN l.event_type =
                            'student.intervention.action_completed'
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'action_id',
                            'action_type',
                            'previous_status',
                            'status',
                            'severity',
                            'sensitivity',
                            'assigned_role_code',
                            'assigned_user_id',
                            'due_at',
                            'completion_note_recorded'
                        ]::text[]
                        WHEN l.event_type =
                            'student.intervention.followup_recorded'
                        THEN ARRAY[
                            'student_profile_id',
                            'intervention_id',
                            'followup_id',
                            'followup_type',
                            'severity',
                            'sensitivity',
                            'observed_at'
                        ]::text[]
                        ELSE NULL::text[]
                    END AS allowed_payload_keys
                FROM public.event_ledger l
                WHERE l.organization_id = p_organization_id
                  AND l.institution_id = p_institution_id
                  AND l.position > v_after_position
                ORDER BY l.position
                LIMIT v_limit
            )
            SELECT
                s.id,
                s.position,
                s.organization_id,
                s.institution_id,
                s.event_type,
                s.event_version,
                s.aggregate_type,
                s.aggregate_id,
                s.actor_user_id,
                s.correlation_id,
                s.causation_id,
                CASE
                    WHEN s.allowed_payload_keys IS NULL
                    THEN '{}'::jsonb
                    WHEN pg_catalog.jsonb_typeof(s.raw_payload_json) <> 'object'
                    THEN NULL::jsonb
                    ELSE COALESCE(
                        (
                            SELECT pg_catalog.jsonb_object_agg(
                                payload_item.key,
                                payload_item.value
                            )
                            FROM pg_catalog.jsonb_each(
                                s.raw_payload_json
                            ) AS payload_item(key, value)
                            WHERE payload_item.key =
                                ANY(s.allowed_payload_keys)
                        ),
                        '{}'::jsonb
                    )
                END AS payload_json,
                s.occurred_at,
                s.recorded_at
            FROM source_rows s
            ORDER BY s.position;
        END;
        $function$
        """
    )

    op.execute(
        f"REVOKE ALL ON FUNCTION {FUNCTION_SIGNATURE} FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {FUNCTION_SIGNATURE} TO education_app"
    )


def downgrade() -> None:
    op.execute(
        f"REVOKE ALL ON FUNCTION {FUNCTION_SIGNATURE} FROM education_app"
    )
    op.execute(
        f"DROP FUNCTION IF EXISTS {FUNCTION_SIGNATURE}"
    )
