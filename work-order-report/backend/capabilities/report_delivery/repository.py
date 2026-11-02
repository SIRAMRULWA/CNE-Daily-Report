"""PostgreSQL adapter for report subscriptions and delivery executions."""

from __future__ import annotations

from datetime import date

from psycopg2.extras import Json

from pipeline.db import get_cursor, run_query


class ReportDeliveryRepository:
    def list_subscriptions(self) -> list[dict]:
        return run_query(
            "SELECT * FROM config.report_email_subscriptions "
            "WHERE NOT deleted "
            "ORDER BY division, assignee_group NULLS FIRST, name"
        )

    def list_enabled_subscriptions(self) -> list[dict]:
        return run_query(
            "SELECT * FROM config.report_email_subscriptions "
            "WHERE enabled AND NOT deleted ORDER BY id"
        )

    def create_subscription(self, values: dict, actor: str) -> dict:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO config.report_email_subscriptions
                   (name, division, assignee_group, recipients, cc_recipients,
                    frequency, weekday, send_time, timezone, attachment_format,
                    enabled, created_by, updated_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING *""",
                (
                    values["name"], values["division"], values.get("assignee_group"),
                    Json(values["recipients"]), Json(values["cc_recipients"]),
                    values["frequency"], values.get("weekday"), values["send_time"],
                    values["timezone"], values["attachment_format"], values["enabled"],
                    actor, actor,
                ),
            )
            return dict(cur.fetchone())

    def replace_subscription(
        self, subscription_id: int, values: dict, actor: str
    ) -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE config.report_email_subscriptions SET
                   name=%s, division=%s, assignee_group=%s, recipients=%s,
                   cc_recipients=%s, frequency=%s, weekday=%s, send_time=%s,
                   timezone=%s, attachment_format=%s, enabled=%s, updated_by=%s,
                   updated_at=NOW()
                   WHERE id=%s AND NOT deleted RETURNING *""",
                (
                    values["name"], values["division"], values.get("assignee_group"),
                    Json(values["recipients"]), Json(values["cc_recipients"]),
                    values["frequency"], values.get("weekday"), values["send_time"],
                    values["timezone"], values["attachment_format"], values["enabled"],
                    actor, subscription_id,
                ),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def set_enabled(
        self, subscription_id: int, enabled: bool, actor: str
    ) -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE config.report_email_subscriptions
                   SET enabled=%s, updated_by=%s, updated_at=NOW()
                   WHERE id=%s AND NOT deleted RETURNING *""",
                (enabled, actor, subscription_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def soft_delete_subscription(self, subscription_id: int, actor: str) -> bool:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE config.report_email_subscriptions
                   SET enabled=FALSE, deleted=TRUE, updated_by=%s, updated_at=NOW()
                   WHERE id=%s AND NOT deleted RETURNING id""",
                (actor, subscription_id),
            )
            return cur.fetchone() is not None

    def list_deliveries(self, limit: int) -> list[dict]:
        return run_query(
            """SELECT d.*, s.name AS subscription_name, s.division, s.assignee_group
               FROM reporting.report_email_deliveries d
               LEFT JOIN config.report_email_subscriptions s
                 ON s.id=d.subscription_id
               ORDER BY d.started_at DESC LIMIT %s""",
            (limit,),
        )

    def latest_report_date(
        self, division: str, assignee_group: str | None
    ) -> date | None:
        params: list[object] = [division]
        extra = ""
        if assignee_group:
            extra = " AND assignee_group=%s"
            params.append(assignee_group)
        rows = run_query(
            f"""SELECT MAX(report_date) AS report_date
                FROM reporting.daily_report_summary
                WHERE report_group=%s {extra}
                  AND EXISTS (
                      SELECT 1 FROM config.division_groups configured
                      WHERE configured.division =
                            reporting.daily_report_summary.report_group
                        AND configured.assignee_group =
                            reporting.daily_report_summary.assignee_group
                        AND configured.active
                  )""",
            tuple(params),
        )
        return rows[0]["report_date"] if rows else None

    def start_manual_delivery(
        self, report_date: date, recipients: list[str], actor: str
    ) -> int:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO reporting.report_email_deliveries
                   (subscription_id, report_date, status, recipients,
                    delivery_mode, requested_by)
                   VALUES (NULL,%s,'SENDING',%s,'MANUAL',%s) RETURNING id""",
                (report_date, Json(recipients), actor),
            )
            return cur.fetchone()["id"]

    def complete_manual_delivery(
        self, delivery_id: int, record_count: int, provider: str,
        message_id: str | None,
    ) -> None:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE reporting.report_email_deliveries
                   SET status='SENT', record_count=%s, provider=%s,
                       provider_message_id=%s, completed_at=NOW()
                   WHERE id=%s""",
                (record_count, provider, message_id, delivery_id),
            )

    def fail_manual_delivery(self, delivery_id: int, error: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                """UPDATE reporting.report_email_deliveries
                   SET status='FAILED', error_message=%s, completed_at=NOW()
                   WHERE id=%s""",
                (error[:2000], delivery_id),
            )

