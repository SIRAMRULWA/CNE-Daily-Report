"""PostgreSQL persistence adapter for Task Reminders."""

from __future__ import annotations

import json

from psycopg2.extras import Json

from pipeline.db import get_cursor, run_query


class TaskReminderRepository:
    def list_subscriptions(self, limit: int, offset: int) -> list[dict]:
        return run_query(
            """SELECT * FROM config.task_reminder_subscriptions
               WHERE NOT deleted
               ORDER BY division,assignee_group NULLS FIRST,name
               LIMIT %s OFFSET %s""",
            (limit, offset),
        )

    def list_enabled_subscriptions(self) -> list[dict]:
        return run_query(
            """SELECT * FROM config.task_reminder_subscriptions
               WHERE enabled AND NOT deleted ORDER BY id"""
        )

    def get_subscription(self, subscription_id: int) -> dict | None:
        rows = run_query(
            """SELECT * FROM config.task_reminder_subscriptions
               WHERE id=%s AND NOT deleted""",
            (subscription_id,),
        )
        return rows[0] if rows else None

    def create_subscription(self, values: dict, actor: str) -> dict:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO config.task_reminder_subscriptions
                   (name,division,assignee_group,recipients,cc_recipients,subject,
                    frequency,weekday,send_time,timezone,max_records,enabled,
                    created_by,updated_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING *""",
                (
                    values["name"], values["division"], values.get("assignee_group"),
                    Json(values["recipients"]), Json(values["cc_recipients"]),
                    values.get("subject"), values["frequency"], values.get("weekday"),
                    values["send_time"], values["timezone"], values["max_records"],
                    values["enabled"], actor, actor,
                ),
            )
            return dict(cur.fetchone())

    def replace_subscription(
        self, subscription_id: int, values: dict, actor: str
    ) -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE config.task_reminder_subscriptions
                   SET name=%s,division=%s,assignee_group=%s,recipients=%s,
                       cc_recipients=%s,subject=%s,frequency=%s,weekday=%s,
                       send_time=%s,timezone=%s,max_records=%s,enabled=%s,
                       updated_by=%s,updated_at=NOW()
                   WHERE id=%s AND NOT deleted RETURNING *""",
                (
                    values["name"], values["division"], values.get("assignee_group"),
                    Json(values["recipients"]), Json(values["cc_recipients"]),
                    values.get("subject"), values["frequency"], values.get("weekday"),
                    values["send_time"], values["timezone"], values["max_records"],
                    values["enabled"], actor, subscription_id,
                ),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def set_enabled(
        self, subscription_id: int, enabled: bool, actor: str
    ) -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE config.task_reminder_subscriptions
                   SET enabled=%s,updated_by=%s,updated_at=NOW()
                   WHERE id=%s AND NOT deleted RETURNING *""",
                (enabled, actor, subscription_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def soft_delete(self, subscription_id: int, actor: str) -> bool:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE config.task_reminder_subscriptions
                   SET enabled=FALSE,deleted=TRUE,updated_by=%s,updated_at=NOW()
                   WHERE id=%s AND NOT deleted RETURNING id""",
                (actor, subscription_id),
            )
            return cur.fetchone() is not None

    def list_executions(
        self, subscription_id: int | None, status: str | None,
        limit: int, offset: int,
    ) -> list[dict]:
        conditions = ["1=1"]
        params: list[object] = []
        if subscription_id:
            conditions.append("e.subscription_id=%s")
            params.append(subscription_id)
        if status:
            conditions.append("e.status=%s")
            params.append(status)
        params.extend([limit, offset])
        return run_query(
            f"""SELECT e.*,s.name AS subscription_name,s.division,s.assignee_group
                FROM reporting.task_reminder_executions e
                JOIN config.task_reminder_subscriptions s
                  ON s.id=e.subscription_id
                WHERE {' AND '.join(conditions)}
                ORDER BY e.started_at DESC LIMIT %s OFFSET %s""",
            tuple(params),
        )

    def claim_execution(
        self, subscription_id: int, idempotency_key: str, trigger_source: str,
        recipients: list[str], requested_by: str,
    ) -> tuple[dict, bool]:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO reporting.task_reminder_executions
                   (subscription_id,idempotency_key,trigger_source,status,
                    recipients,requested_by)
                   VALUES (%s,%s,%s,'RUNNING',%s::jsonb,%s)
                   ON CONFLICT (subscription_id,idempotency_key)
                   DO NOTHING RETURNING *""",
                (
                    subscription_id, idempotency_key, trigger_source,
                    json.dumps(recipients), requested_by,
                ),
            )
            row = cur.fetchone()
        if row:
            return dict(row), False
        existing = run_query(
            """SELECT * FROM reporting.task_reminder_executions
               WHERE subscription_id=%s AND idempotency_key=%s""",
            (subscription_id, idempotency_key),
        )
        return existing[0], True

    def complete_execution(
        self, execution_id: int, record_count: int, attention_count: int,
        provider: str, message_id: str | None,
    ) -> dict:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE reporting.task_reminder_executions
                   SET status='SENT',record_count=%s,attention_count=%s,
                       provider=%s,provider_message_id=%s,completed_at=NOW()
                   WHERE id=%s RETURNING *""",
                (
                    record_count, attention_count, provider, message_id,
                    execution_id,
                ),
            )
            return dict(cur.fetchone())

    def fail_execution(
        self, execution_id: int, error_code: str, error_message: str
    ) -> None:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE reporting.task_reminder_executions
                   SET status='FAILED',error_code=%s,error_message=%s,
                       completed_at=NOW() WHERE id=%s""",
                (error_code, error_message[:2000], execution_id),
            )

