"""Generate branded Daily Report email bodies and FE-matched attachments."""

import csv
import html
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO, StringIO
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from capabilities.daily_reports import email_report_data
from notifications.transport import Attachment


# Backend email attachment contract. It starts with the FE drill-down export
# columns and adds operational source timestamps required by email recipients.
EXPORT_COLUMNS = [
    ("sla_status", "SLA", 16),
    ("request_id", "Request ID", 16),
    ("task_id", "Task ID", 16),
    ("report_category", "Category", 16),
    ("priority", "Priority", 16),
    ("status", "Status", 18),
    ("assignee_group", "Group", 28),
    ("assignee", "Assignee", 16),
    ("hours_open", "Hours Open", 16),
    ("create_date", "Create Date", 20),
    ("assign_time", "Assign Time", 20),
    ("scheduled_start", "Scheduled Start Date", 22),
    ("scheduled_end", "Scheduled End", 16),
    ("summary", "Summary", 48),
]
CLOSED_CHANGE_COLUMNS = [
    column for column in EXPORT_COLUMNS if column[0] != "sla_status"
] + [
    ("status_reason", "Status Reason", 22),
    ("closed_time", "Closed Time", 20),
]
RECORD_COLUMNS = [column[0] for column in EXPORT_COLUMNS]
HOURS_OPEN_COLUMN = next(
    index for index, (key, _label, _width) in enumerate(EXPORT_COLUMNS, start=1)
    if key == "hours_open"
)

# Matches the SLA palette used by the frontend Records export.
SLA_ROW_COLOURS = {
    "BREACHED": ("FFF0F0", "CC0000"),
    "NEARING_SLA": ("FFF8E6", "C47000"),
    "NO_SCHEDULE": ("EEF4FF", "0057A8"),
    "NO_ASSIGN_TIME": ("F4EAF7", "6A1B75"),
    "WITHIN_SLA": ("EDF7ED", "0A7A0A"),
    "CLOSED": ("F0F0F0", "5C5C5C"),
}
INVALID_SHEET_TITLE = re.compile(r"[\\/*?:\[\]]")


def report_data(report_date: date, division: str, assignee_group: str | None) -> tuple[list[dict], list[dict]]:
    """Compatibility function delegating snapshot access to the capability."""
    return email_report_data(report_date, division, assignee_group)


def _metrics(summary: list[dict]) -> dict:
    by_band: dict[str, list[dict]] = {}
    for row in summary:
        by_band.setdefault(str(row.get("sla_band") or ""), []).append(row)

    def total(band: str, key: str = "total_count") -> int:
        return sum(int(row.get(key) or 0) for row in by_band.get(band, []))

    total_open = total("Total Open Calls")
    nearing = total("Calls Nearing SLA")
    breached = total("Breached Calls")
    closed_success_yesterday = total("Closed Successfully Yesterday")
    groups: dict[str, dict[str, int]] = {}
    for row in summary:
        group = str(row.get("assignee_group") or "Unassigned")
        band = str(row.get("sla_band") or "")
        group_metrics = groups.setdefault(group, {
            "open": 0, "nearing": 0, "breached": 0,
            "bands": {},
        })
        band_metrics = group_metrics["bands"].setdefault(band, {
            "incident": 0, "change": 0, "access": 0, "event": 0, "total": 0,
        })
        for target, source in (
            ("incident", "incident_count"), ("change", "change_count"),
            ("access", "access_count"), ("event", "event_count"),
            ("total", "total_count"),
        ):
            band_metrics[target] += int(row.get(source) or 0)
        if band == "Total Open Calls":
            group_metrics["open"] += int(row.get("total_count") or 0)
        elif band == "Calls Nearing SLA":
            group_metrics["nearing"] += int(row.get("total_count") or 0)
        elif band == "Breached Calls":
            group_metrics["breached"] += int(row.get("total_count") or 0)

    return {
        "total_open": total_open,
        "nearing": nearing,
        "breached": breached,
        "closed_success_yesterday": closed_success_yesterday,
        "within": max(total_open - nearing - breached, 0),
        "incidents": total("Total Open Calls", "incident_count"),
        "changes": total("Total Open Calls", "change_count"),
        "access": total("Total Open Calls", "access_count"),
        "events": total("Total Open Calls", "event_count"),
        "groups": groups,
    }


def _pct(value: int, total: int) -> str:
    return f"{(value / total * 100):.1f}%" if total else "0.0%"


def reminder_html_body(generated_at: datetime, division: str, assignee_group: str | None,
                       summary: list[dict], record_count: int, oldest_days: int) -> str:
    """Render the simplified, action-focused task reminder (no CTA button)."""
    workspace_zone = ZoneInfo(os.getenv("WORKSPACE_TIMEZONE", "Africa/Johannesburg"))
    generated_at = (
        generated_at.replace(tzinfo=workspace_zone)
        if generated_at.tzinfo is None
        else generated_at.astimezone(workspace_zone)
    )
    metrics = _metrics(summary)
    scope = f"{division} / {assignee_group}" if assignee_group else division
    filename = f"daily-report-{division.lower()}-{generated_at.date().isoformat()}.xlsx"

    group_rows = ""
    for group, values in sorted(metrics["groups"].items()):
        group_rows += f"""<tr>
          <td style="padding:9px 12px;font-size:12.5px;color:#1A1A1A;border-top:1px solid #E5E5E5">{html.escape(group)}</td>
          <td align="center" style="padding:9px 8px;font-size:12.5px;font-weight:bold;color:#0A7A0A;background:#EDF7ED;border-top:1px solid #B8DFB8">{values['open']}</td>
          <td align="center" style="padding:9px 8px;font-size:12.5px;font-weight:bold;color:#C47000;background:#FFF8E6;border-top:1px solid #F5D580">{values['nearing']}</td>
          <td align="center" style="padding:9px 12px;font-size:12.5px;font-weight:bold;color:#CC0000;background:#FFF0F0;border-top:1px solid #F5B8B8">{values['breached']}</td>
        </tr>"""
    if not group_rows:
        group_rows = '<tr><td colspan="4" style="padding:14px 12px;font-size:11px;color:#737373;border-top:1px solid #ececee">No eligible open tasks were returned.</td></tr>'

    return f"""<!doctype html><html><body style="margin:0;background:#eff0f2;padding:24px 8px;color:#1A1A1A">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;margin:0 auto;background:#FFFFFF;border-collapse:collapse;border:1px solid #e6e6e8;border-radius:10px;overflow:hidden;font-family:Arial,'Segoe UI',sans-serif;color:#1A1A1A">
      <tr><td style="background:#e60000;padding:20px 28px"><table role="presentation" width="100%"><tr>
        <td width="46"><img src="cid:vodacom-logo" width="32" height="32" alt="Vodacom" style="display:block;width:32px;height:32px;border:0;border-radius:50%;background:#ffffff"></td>
        <td><div style="font-size:17px;font-weight:bold;color:#ffffff">{html.escape(division)} Tasks Reminder</div></td>
        <td align="right"><div style="font-size:11px;color:#ffd9d9;font-weight:600">{generated_at.strftime('%d %b %Y &middot; %H:%M %Z')}</div></td>
      </tr></table></td></tr>
      <tr><td style="padding:22px 28px 4px 28px">
        <p style="margin:0;font-size:14.5px;color:#1A1A1A;line-height:1.6">Hi Team, you have <strong style="color:#0A7A0A">{metrics['total_open']} open tasks</strong> that need action{f", including <strong style=\"color:#CC0000\">{metrics['breached']} breached</strong> and <strong style=\"color:#C47000\">{metrics['nearing']} nearing SLA</strong>" if metrics['total_open'] else ""}. Please review, update Helix, and close what's resolved.</p>
      </td></tr>
      <tr><td style="padding:20px 28px 4px 28px">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #ececee;border-radius:10px;overflow:hidden">
          <tr>
            <td width="25%" align="center" style="padding:14px 5px;background:#EDF7ED;border-right:1px solid #B8DFB8"><div style="font-size:22px;font-weight:bold;color:#0A7A0A">{metrics['total_open']}</div><div style="font-size:9px;font-weight:bold;color:#0A7A0A;text-transform:uppercase;letter-spacing:.4px;padding-top:2px">Open Tasks</div></td>
            <td width="25%" align="center" style="padding:14px 5px;background:#FFF0F0;border-right:1px solid #F5B8B8"><div style="font-size:22px;font-weight:bold;color:#CC0000">{metrics['breached']}</div><div style="font-size:9px;font-weight:bold;color:#CC0000;text-transform:uppercase;letter-spacing:.4px;padding-top:2px">Breached</div></td>
            <td width="25%" align="center" style="padding:14px 5px;background:#FFF8E6;border-right:1px solid #F5D580"><div style="font-size:22px;font-weight:bold;color:#C47000">{metrics['nearing']}</div><div style="font-size:9px;font-weight:bold;color:#C47000;text-transform:uppercase;letter-spacing:.4px;padding-top:2px">Near SLA</div></td>
            <td width="25%" align="center" style="padding:14px 5px;background:#EEF4FF"><div style="font-size:22px;font-weight:bold;color:#0057A8">{oldest_days}</div><div style="font-size:9px;font-weight:bold;color:#0057A8;text-transform:uppercase;letter-spacing:.4px;padding-top:2px">Oldest (Days)</div></td>
          </tr>
        </table>
      </td></tr>
      <tr><td style="padding:22px 28px 4px 28px">
        <div style="font-size:11px;font-weight:bold;color:#8a8f98;text-transform:uppercase;letter-spacing:.5px;padding-bottom:8px">By Group</div>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #ececee;border-radius:8px;border-collapse:collapse">
          <tr>
            <td style="padding:8px 12px;font-size:11px;font-weight:bold;color:#5C5C5C;background:#F5F5F5">GROUP</td>
            <td align="center" style="padding:8px 8px;font-size:11px;font-weight:bold;color:#0A7A0A;background:#EDF7ED">OPEN</td>
            <td align="center" style="padding:8px 8px;font-size:11px;font-weight:bold;color:#C47000;background:#FFF8E6">NEAR</td>
            <td align="center" style="padding:8px 12px;font-size:11px;font-weight:bold;color:#CC0000;background:#FFF0F0">BREACHED</td>
          </tr>
          {group_rows}
        </table>
      </td></tr>
      <tr><td style="padding:18px 28px 4px 28px">
        <p style="margin:0;font-size:12px;color:#8a8f98;line-height:1.6">Full task-level detail is in the attached <strong style="color:#555555">{filename}</strong> ({record_count} records, Daily Report format).</p>
      </td></tr>
      <tr><td style="padding:22px 28px 24px 28px;border-top:1px solid #f0f0f0;margin-top:8px">
        <p style="margin:0;font-size:11px;color:#aeb2b9;line-height:1.6">Automated reminder from the INTSS Task Reporting Platform (live Helix data). Questions? Contact the INTSS Reporting Team.<br>
        Reminder ID: {html.escape(division)}-{generated_at.strftime('%Y%m%d-%H%M')}</p>
      </td></tr>
    </table></body></html>"""


def html_body(name: str, report_date: date, division: str, assignee_group: str | None,
              summary: list[dict], record_count: int | None = None,
              attachment_format: str = "XLSX") -> str:
    """Return the Outlook-safe inner email body from the approved FE design."""
    metrics = _metrics(summary)
    scope = f"{division} / {assignee_group}" if assignee_group else division
    generated = datetime.now()
    closure_date = report_date - timedelta(days=1)
    schedule_hour = int(os.getenv("PIPELINE_SCHEDULE_HOUR", "7"))
    closure_window_label = (
        f"{closure_date.strftime('%d %B %Y')} {schedule_hour:02d}:00 to "
        f"{report_date.strftime('%d %B %Y')} {schedule_hour:02d}:00"
    )
    extension = "csv" if attachment_format == "CSV" else "xlsx"
    filename = f"daily-report-{division.lower()}-{report_date.isoformat()}.{extension}"
    band_config = (
        ("Total Open Calls", "Total Open", "#EDF7ED", "#0A7A0A"),
        ("Calls Nearing SLA", "Nearing SLA", "#FFF8E6", "#C47000"),
        ("Breached Calls", "Breached", "#FFF0F0", "#CC0000"),
        ("Closed Successfully Yesterday", "Closed Successfully Yesterday", "#EAF7F4", "#007C6C"),
    )
    group_blocks = ""
    for group, values in sorted(metrics["groups"].items()):
        rows = ""
        for band, label, background, colour in band_config:
            counts = values["bands"].get(band, {})
            cells = "".join(
                f'<td align="right" style="padding:9px 10px;border-bottom:1px solid #eeeeee;font-size:11px;font-weight:bold;color:{colour}">{counts.get(key, 0)}</td>'
                for key in ("incident", "change", "access", "event", "total")
            )
            rows += f'<tr style="background:{background}"><td style="padding:9px 10px;border-bottom:1px solid #eeeeee;font-size:10px;font-weight:bold;color:{colour}">{label}</td>{cells}</tr>'
        group_blocks += f"""<tr><td style="padding:18px 0 6px;font-size:12px;font-weight:bold;color:#1A1A1A">{html.escape(group)}</td></tr>
        <tr><td><table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #E5E5E5;border-collapse:collapse">
          <tr style="background:#F5F5F5"><th align="left" style="padding:8px 10px;font-size:9px;color:#5C5C5C;text-transform:uppercase">SLA position</th><th align="right" style="padding:8px 10px;font-size:9px;color:#5C5C5C">INCIDENT</th><th align="right" style="padding:8px 10px;font-size:9px;color:#5C5C5C">CHANGE</th><th align="right" style="padding:8px 10px;font-size:9px;color:#5C5C5C">ACCESS</th><th align="right" style="padding:8px 10px;font-size:9px;color:#5C5C5C">EVENT</th><th align="right" style="padding:8px 10px;font-size:9px;color:#5C5C5C">TOTAL</th></tr>
          {rows}</table></td></tr>"""
    count = metrics["total_open"] if record_count is None else record_count
    return f"""<!doctype html><html><body style="margin:0;background:#F3F5F7;padding:24px 8px;color:#1A1A1A">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:760px;margin:0 auto;background:#FFFFFF;border-collapse:collapse;font-family:Arial,'Segoe UI',sans-serif;color:#1A1A1A">
      <tr><td style="height:6px;background:#e60000;font-size:0;line-height:0">&nbsp;</td></tr>
      <tr><td style="padding:24px 30px 18px;border-bottom:1px solid #e5e5e5"><table role="presentation" width="100%"><tr>
        <td width="58"><img src="cid:vodacom-logo" width="46" height="46" alt="Vodacom" style="display:block;width:46px;height:46px;border:0"></td>
        <td><div style="font-size:19px;font-weight:bold">{html.escape(division)} Daily Report</div><div style="font-size:11px;color:#737373;margin-top:4px">Daily Reports &bull; Official reporting snapshot</div></td>
        <td align="right"><span style="display:inline-block;background:#fff0f0;color:#cc0000;border:1px solid #f5b8b8;border-radius:14px;padding:5px 10px;font-size:10px;font-weight:bold">{html.escape(scope)}</span></td>
      </tr></table></td></tr>
      <tr><td style="padding:24px 30px 8px"><div style="font-size:11px;color:#737373;text-transform:uppercase;letter-spacing:.7px;font-weight:bold">{report_date.strftime('%A, %d %B %Y')}</div><div style="font-size:22px;font-weight:bold;margin-top:6px">Daily Report Breakdown</div><p style="font-size:12px;line-height:1.6;color:#525252;margin:8px 0 0">Official {html.escape(scope)} snapshot, grouped by assignee group and service category. The attached {html.escape(attachment_format)} file contains the complete record-level data.</p></td></tr>
      <tr><td style="padding:18px 30px 8px"><table role="presentation" width="100%"><tr>
        <td width="32%" style="padding:14px 12px;background:#EDF7ED;border:1px solid #B8DFB8"><div style="font-size:9px;color:#0A7A0A;text-transform:uppercase;font-weight:bold">Total Open Calls</div><div style="font-size:25px;font-weight:bold;color:#0A7A0A;margin-top:5px">{metrics['total_open']}</div><div style="font-size:9px;color:#0A7A0A;margin-top:3px">Across {len(metrics['groups'])} groups</div></td><td width="2%">&nbsp;</td>
        <td width="32%" style="padding:14px 12px;background:#FFF8E6;border:1px solid #F5D580"><div style="font-size:9px;color:#C47000;text-transform:uppercase;font-weight:bold">Calls Nearing SLA</div><div style="font-size:25px;font-weight:bold;color:#C47000;margin-top:5px">{metrics['nearing']}</div><div style="font-size:9px;color:#C47000;margin-top:3px">{_pct(metrics['nearing'], metrics['total_open'])} of open</div></td><td width="2%">&nbsp;</td>
        <td width="32%" style="padding:14px 12px;background:#FFF0F0;border:1px solid #F5B8B8"><div style="font-size:9px;color:#CC0000;text-transform:uppercase;font-weight:bold">Breached Calls</div><div style="font-size:25px;font-weight:bold;color:#CC0000;margin-top:5px">{metrics['breached']}</div><div style="font-size:9px;color:#CC0000;margin-top:3px">Requires attention</div></td>
      </tr></table></td></tr>
      <tr><td style="padding:4px 30px 8px"><table role="presentation" width="100%"><tr>
        <td style="padding:14px 12px;background:#EAF7F4;border:1px solid #A8DCD3"><div style="font-size:9px;color:#007C6C;text-transform:uppercase;font-weight:bold">Closed Successfully Yesterday</div><div style="font-size:25px;font-weight:bold;color:#007C6C;margin-top:5px">{metrics['closed_success_yesterday']}</div><div style="font-size:9px;color:#007C6C;margin-top:3px">Status Reason: Success &bull; 24-hour window: {closure_window_label}</div></td>
      </tr></table></td></tr>
      <tr><td style="padding:8px 30px 18px"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">{group_blocks}</table></td></tr>
      <tr><td style="padding:18px 30px"><table role="presentation" width="100%" style="background:#fafafa;border:1px solid #e5e5e5"><tr><td style="padding:14px"><div style="font-size:11px;font-weight:bold">{filename}</div><div style="font-size:9px;color:#737373;margin-top:3px">{html.escape(attachment_format)} attachment &bull; Complete record-level snapshot &bull; {count} records</div></td><td align="right" style="padding:14px;font-size:9px;color:#0a7a0a;font-weight:bold">ATTACHED</td></tr></table></td></tr>
      <tr><td style="padding:18px 30px 24px;border-top:1px solid #e5e5e5"><p style="margin:0;font-size:10px;line-height:1.55;color:#737373">This is an automated operational report generated from the approved Daily Report snapshot. Please do not reply to this mailbox. For data queries, contact the INTSS Service Delivery team.</p><table role="presentation" width="100%" style="margin-top:16px"><tr><td style="font-size:10px;font-weight:bold;color:#e60000">Vodacom Core Operations Reporting</td><td align="right" style="font-size:9px;color:#9a9a9a">Report ID: {html.escape(division)}-{generated.strftime('%Y%m%d-%H%M')}</td></tr></table></td></tr>
    </table></body></html>"""


def _normalised_hours(value):
    """Return a finite two-decimal numeric value suitable for Excel sorting."""
    if value in (None, ""):
        return ""
    try:
        hours = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if not hours.is_finite():
        return ""
    return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _export_value(key: str, value):
    if key == "hours_open":
        return _normalised_hours(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return "" if value is None else value


def _sheet_title(group: str, used_titles: set[str]) -> str:
    """Return an Excel-safe, case-insensitively unique worksheet title."""
    base = INVALID_SHEET_TITLE.sub("-", group).strip().strip("'") or "Unassigned"
    base = base[:31]
    title = base
    suffix_number = 2
    while title.casefold() in used_titles:
        suffix = f" ({suffix_number})"
        title = f"{base[:31 - len(suffix)]}{suffix}"
        suffix_number += 1
    used_titles.add(title.casefold())
    return title


def _populate_sheet(sheet, records: list[dict], labels: list[str],
                    columns=EXPORT_COLUMNS) -> None:
    sheet.append(labels)
    for record in records:
        sheet.append([_export_value(key, record.get(key)) for key, _label, _width in columns])
        row = sheet[sheet.max_row]
        sheet.cell(sheet.max_row, HOURS_OPEN_COLUMN).number_format = "0.00"
        colours = SLA_ROW_COLOURS.get(str(record.get("sla_status") or ""))
        if colours:
            background, text = colours
            for cell in row:
                cell.fill = PatternFill("solid", fgColor=background)
            row[0].font = Font(color=text, bold=True)
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="E60000")
        cell.font = Font(color="FFFFFF", bold=True)
    for index, (_key, _label, width) in enumerate(columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    last_column = get_column_letter(len(columns))
    sheet.auto_filter.ref = f"A1:{last_column}{max(sheet.max_row, 1)}"


def attachment(records: list[dict], division: str, report_date: date, file_format: str,
               closed_changes: list[dict] | None = None) -> Attachment:
    base = f"daily-report-{division.lower()}-{report_date.isoformat()}"
    labels = [column[1] for column in EXPORT_COLUMNS]
    if file_format == "CSV":
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(labels)
        writer.writerows(
            [_export_value(key, record.get(key)) for key, _label, _width in EXPORT_COLUMNS]
            for record in records
        )
        return Attachment(f"{base}.csv", output.getvalue().encode("utf-8-sig"), "text", "csv")

    workbook = Workbook()
    workbook.properties.creator = "Daily Report Raw Data"
    records_by_group: dict[str, list[dict]] = {}
    for record in records:
        group = str(record.get("assignee_group") or "Unassigned")
        records_by_group.setdefault(group, []).append(record)

    if not records_by_group:
        sheet = workbook.active
        sheet.title = "Raw Data"
        _populate_sheet(sheet, [], labels)
    else:
        used_titles: set[str] = set()
        for index, (group, group_records) in enumerate(
            sorted(records_by_group.items(), key=lambda item: item[0].casefold())
        ):
            sheet = workbook.active if index == 0 else workbook.create_sheet()
            sheet.title = _sheet_title(group, used_titles)
            _populate_sheet(sheet, group_records, labels)
    if closed_changes is not None:
        sheet = workbook.create_sheet("Closed Changes")
        _populate_sheet(
            sheet,
            closed_changes,
            [column[1] for column in CLOSED_CHANGE_COLUMNS],
            CLOSED_CHANGE_COLUMNS,
        )
    output = BytesIO()
    workbook.save(output)
    return Attachment(f"{base}.xlsx", output.getvalue(), "application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
