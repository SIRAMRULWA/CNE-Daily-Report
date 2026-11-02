"use client";

import { Fragment, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { usePathname } from "next/navigation";
import {
  AlertTriangle,
  Activity,
  CheckCircle2,
  Clock,
  Download,
  Printer,
  RefreshCw,
  X,
} from "lucide-react";
import { dailyReportApi } from "@/lib/api";
import { useReportDate } from "@/lib/report-date-context";
import { cn, fmtDate, fmtHours } from "@/lib/utils";
import {
  Btn,
  CategoryChip,
  EmptyState,
  KpiCard,
  PageHeader,
  PriorityChip,
  SlaBadge,
  Tag,
} from "@/components/ui";
import type {
  Category,
  DailyReportKpis,
  DailyReportLiveRecord,
  DailyReportRow,
  SlaStatus,
} from "@/types";

interface ReportConfig {
  slug: string;
  navLabel: string;
  title: string;
  division?: string;
}

const KNOWN_REPORTS: Record<string, ReportConfig> = {
  intss: {
    slug: "intss",
    navLabel: "INTSS",
    title: "INTSS Daily Report",
    division: "INTSS",
  },
  nsd: {
    slug: "nsd",
    navLabel: "NSD",
    title: "NSD Daily Report",
    division: "NSD",
  },
  cvdi: {
    slug: "cvdi",
    navLabel: "CVDI",
    title: "CVDI Daily Report",
    division: "CVDI",
  },
  cdn: {
    slug: "cdn",
    navLabel: "CDN",
    title: "CDN Daily Report",
    division: "CDN",
  },
};

const SLA_BANDS = [
  "Total Open Calls",
  "Calls Nearing SLA",
  "Breached Calls",
  "Closed Successfully Yesterday",
] as const;
type Band = (typeof SLA_BANDS)[number];

interface GroupBandRow {
  incident: number;
  change: number;
  access: number;
  event: number;
  total: number;
}

interface GroupMatrix {
  [assigneeGroup: string]: Partial<Record<Band, GroupBandRow>>;
}

interface DivisionMatrix {
  [division: string]: GroupMatrix;
}

interface DrilldownSelection {
  title: string;
  division?: string;
  assignee_group?: string;
  sla?: SlaStatus;
  category?: Category;
}

const CATEGORY_BY_COLUMN: Record<keyof GroupBandRow, Category | undefined> = {
  incident: "INCIDENT",
  change: "CHANGE",
  access: "ACCESS",
  event: "EVENT",
  total: undefined,
};

const BAND_STYLE: Record<
  Band,
  {
    rowBg: string;
    labelBg: string;
    labelText: string;
    label: string;
    totalText: string;
  }
> = {
  "Total Open Calls": {
    rowBg: "",
    labelBg: "bg-[#EDF7ED]",
    labelText: "text-[#0A7A0A]",
    label: "Total Open Calls",
    totalText: "text-[#0A7A0A]",
  },
  "Calls Nearing SLA": {
    rowBg: "bg-[#FFFCF0]",
    labelBg: "bg-[#FFF8E6]",
    labelText: "text-[#C47000]",
    label: "Calls Nearing SLA",
    totalText: "text-[#C47000]",
  },
  "Breached Calls": {
    rowBg: "bg-[#FFF8F8]",
    labelBg: "bg-[#FFF0F0]",
    labelText: "text-[#CC0000]",
    label: "Breached Calls",
    totalText: "text-[#CC0000]",
  },
  "Closed Successfully Yesterday": {
    rowBg: "bg-[#F2FAF8]",
    labelBg: "bg-[#EAF7F4]",
    labelText: "text-[#007C6C]",
    label: "Closed Successfully Yesterday",
    totalText: "text-[#007C6C]",
  },
};

function reportFromPath(pathname: string): ReportConfig {
  const slug = pathname.split("/").filter(Boolean)[1] ?? "intss";

  const normalizedSlug = decodeURIComponent(slug).toLowerCase();
  return (
    KNOWN_REPORTS[normalizedSlug] ?? {
      slug: normalizedSlug,
      navLabel: normalizedSlug.toUpperCase(),
      title: `${normalizedSlug.toUpperCase()} Daily Report`,
      division: normalizedSlug.toUpperCase(),
    }
  );
}

function buildMatrix(
  rows: DailyReportRow[],
  selectedDivision?: string,
  configuredGroups: string[] = [],
): DivisionMatrix {
  const matrix: DivisionMatrix = {};

  if (selectedDivision && configuredGroups.length) {
    matrix[selectedDivision] = {};
    configuredGroups.forEach((group) => {
      matrix[selectedDivision][group] = {};
    });
  }

  rows.forEach((row) => {
    if (
      selectedDivision &&
      !row.assignee_group &&
      row.report_group === selectedDivision
    )
      return;

    const division = selectedDivision || row.division || "Unassigned Division";
    const group = row.assignee_group || row.report_group || "All groups";

    if (!matrix[division]) matrix[division] = {};
    if (!matrix[division][group]) matrix[division][group] = {};

    matrix[division][group][row.sla_band] = {
      incident: row.incident_count,
      change: row.change_count,
      access: row.access_count,
      event: row.event_count,
      total: row.total_count,
    };
  });

  return matrix;
}

function addClosureFallback(
  matrix: DivisionMatrix,
  closures: DailyReportKpis["successful_closures_by_group"],
): DivisionMatrix {
  closures.forEach((closure) => {
    if (!matrix[closure.division]) matrix[closure.division] = {};
    if (!matrix[closure.division][closure.assignee_group]) {
      matrix[closure.division][closure.assignee_group] = {};
    }
    if (!matrix[closure.division][closure.assignee_group]["Closed Successfully Yesterday"]) {
      matrix[closure.division][closure.assignee_group]["Closed Successfully Yesterday"] = {
        incident: 0,
        change: 0,
        access: 0,
        event: 0,
        total: closure.total_closed_success,
      };
    }
  });
  return matrix;
}

function hasSummaryGroupBreakdown(
  rows: DailyReportRow[],
  selectedDivision?: string,
): boolean {
  if (!selectedDivision || !rows.length) return true;
  return rows.some(
    (row) => row.assignee_group && row.assignee_group !== selectedDivision,
  );
}

function categoryColumn(category: Category | null): keyof GroupBandRow | null {
  if (category === "INCIDENT") return "incident";
  if (category === "CHANGE") return "change";
  if (category === "ACCESS") return "access";
  if (category === "EVENT") return "event";
  return null;
}

function ensureBandRow(
  groupMatrix: GroupMatrix,
  group: string,
  band: Band,
): GroupBandRow {
  if (!groupMatrix[group]) groupMatrix[group] = {};
  if (!groupMatrix[group][band]) {
    groupMatrix[group][band] = {
      incident: 0,
      change: 0,
      access: 0,
      event: 0,
      total: 0,
    };
  }
  return groupMatrix[group][band];
}

function buildLiveMatrix(
  records: DailyReportLiveRecord[],
  selectedDivision?: string,
  configuredGroups: string[] = [],
): DivisionMatrix {
  const matrix: DivisionMatrix = {};
  const fallbackDivision = selectedDivision || "Unassigned Division";

  if (selectedDivision && configuredGroups.length) {
    matrix[selectedDivision] = {};
    configuredGroups.forEach((group) => {
      matrix[selectedDivision][group] = {};
    });
  }

  records.forEach((record) => {
    const division =
      selectedDivision || record.report_group || fallbackDivision;
    const group = record.assignee_group || "Unassigned group";
    const category = categoryColumn(record.report_category);

    if (!category) return;
    if (!matrix[division]) matrix[division] = {};

    const totalOpen = ensureBandRow(
      matrix[division],
      group,
      "Total Open Calls",
    );
    totalOpen[category] += 1;
    totalOpen.total += 1;

    if (record.sla_status === "NEARING_SLA") {
      const nearing = ensureBandRow(
        matrix[division],
        group,
        "Calls Nearing SLA",
      );
      nearing[category] += 1;
      nearing.total += 1;
    }

    if (record.sla_status === "BREACHED") {
      const breached = ensureBandRow(matrix[division], group, "Breached Calls");
      breached[category] += 1;
      breached.total += 1;
    }
  });

  return matrix;
}

function totalsFromKpis(kpis?: DailyReportKpis) {
  return {
    breached: kpis?.total_breached ?? 0,
    nearing: kpis?.total_nearing ?? 0,
    total: kpis?.total_open ?? 0,
    within: kpis?.total_within ?? 0,
    closedSuccessfullyYesterday: kpis?.total_closed_success_yesterday ?? 0,
    incidents: kpis?.total_incidents ?? 0,
    changes: kpis?.total_changes ?? 0,
    access: kpis?.total_access ?? 0,
    events: kpis?.total_events ?? 0,
  };
}

function shortGroupLabel(raw: string): string {
  return raw
    .replace("Appl:", "")
    .replace(":OSS", "")
    .replace(" Operational Support", "")
    .trim();
}

function Val({ v, band }: { v: number; band: Band }) {
  if (!v) return <span className="text-[#BCBCBC] font-400">0</span>;
  const color =
    band === "Closed Successfully Yesterday"
      ? "text-[#007C6C] font-700"
      : band === "Breached Calls"
      ? "text-[#CC0000] font-700"
      : band === "Calls Nearing SLA"
        ? "text-[#C47000] font-600"
        : "text-[#1A1A1A] font-600";
  return <span className={color}>{v}</span>;
}

function slaForBand(band: Band): SlaStatus | undefined {
  if (band === "Breached Calls") return "BREACHED";
  if (band === "Calls Nearing SLA") return "NEARING_SLA";
  return undefined;
}

function ClickableVal({
  v,
  band,
  onClick,
}: {
  v: number;
  band: Band;
  onClick: () => void;
}) {
  if (!v) return <Val v={v} band={band} />;
  if (band === "Closed Successfully Yesterday") return <Val v={v} band={band} />;

  const color =
    band === "Breached Calls"
      ? "text-[#CC0000]"
      : band === "Calls Nearing SLA"
        ? "text-[#C47000]"
        : "text-[#1A1A1A]";

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex min-w-8 justify-end rounded px-1 py-0.5 text-[12px] font-700 underline-offset-2 hover:bg-[#F5F5F5] hover:underline",
        color,
      )}
      title="Open matching records"
    >
      {v}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Investigation / drill-down panel
// ---------------------------------------------------------------------------
// Redesigned around three problems the table-based version had:
//   1. The record table needed 760px of width inside a 560px panel, forcing
//      horizontal + vertical scrolling at once. Replaced with a card list
//      that reflows to any panel width.
//   2. You could not narrow or widen an investigation once open — changing
//      SLA/category meant closing the panel and clicking a different cell.
//      Added chip filters wired back to the parent's selection.
//   3. Results were capped at 250 with no way to search, sort, or see the
//      rest. Added search, sort, and "load more" over the already-fetched
//      record set.

type SortKey = "hours_desc" | "hours_asc" | "priority" | "sla";
type ExportFormat = "pdf" | "excel" | "csv";

const SORT_LABEL: Record<SortKey, string> = {
  hours_desc: "Longest open first",
  hours_asc: "Newest open first",
  priority: "Priority",
  sla: "SLA status",
};

const EXPORT_LABEL: Record<ExportFormat, string> = {
  pdf: "PDF",
  excel: "Excel",
  csv: "CSV",
};

const DRILLDOWN_EXPORT_COLUMNS: Array<{
  label: string;
  value: (record: DailyReportLiveRecord) => string | number;
}> = [
  { label: "SLA", value: (record) => record.sla_status ?? "" },
  { label: "Request ID", value: (record) => record.request_id ?? "" },
  { label: "Task ID", value: (record) => record.task_id ?? "" },
  { label: "Category", value: (record) => record.report_category ?? "" },
  { label: "Priority", value: (record) => record.priority ?? "" },
  { label: "Group", value: (record) => record.assignee_group ?? "" },
  { label: "Assignee", value: (record) => record.assignee ?? "" },
  { label: "Hours Open", value: (record) => record.hours_open ?? "" },
  { label: "Scheduled End", value: (record) => record.scheduled_end ?? "" },
  { label: "Summary", value: (record) => record.summary ?? "" },
];

function slaRank(status: SlaStatus | null | undefined): number {
  if (status === "BREACHED") return 0;
  if (status === "NEARING_SLA") return 1;
  return 2;
}

// Assumes priority values look like "P1".."P5"; falls back to a small set of
// common word-based labels; unrecognised values sort last. Adjust the word
// list below if your Priority type uses different labels.
function priorityRank(priority: string | null | undefined): number {
  if (!priority) return 99;
  const digitMatch = /(\d+)/.exec(priority);
  if (digitMatch) return Number(digitMatch[1]);
  const order = ["critical", "high", "medium", "low"];
  const idx = order.indexOf(priority.toLowerCase());
  return idx === -1 ? 99 : idx;
}

function sortRecords(
  records: DailyReportLiveRecord[],
  sortKey: SortKey,
): DailyReportLiveRecord[] {
  const copy = [...records];
  switch (sortKey) {
    case "hours_desc":
      return copy.sort((a, b) => (b.hours_open ?? 0) - (a.hours_open ?? 0));
    case "hours_asc":
      return copy.sort((a, b) => (a.hours_open ?? 0) - (b.hours_open ?? 0));
    case "priority":
      return copy.sort(
        (a, b) => priorityRank(a.priority) - priorityRank(b.priority),
      );
    case "sla":
      return copy.sort((a, b) => slaRank(a.sla_status) - slaRank(b.sla_status));
    default:
      return copy;
  }
}

function matchesSearch(record: DailyReportLiveRecord, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return Boolean(
    record.request_id?.toLowerCase().includes(q) ||
    record.task_id?.toLowerCase().includes(q) ||
    record.summary?.toLowerCase().includes(q) ||
    record.assignee?.toLowerCase().includes(q) ||
    record.assignee_group?.toLowerCase().includes(q),
  );
}

function csvCell(value: string | number): string {
  return `"${String(value).replace(/"/g, '""')}"`;
}

function recordsToCsv(records: DailyReportLiveRecord[]): string {
  const header = DRILLDOWN_EXPORT_COLUMNS.map((column) => column.label);
  const rows = records.map((record) =>
    DRILLDOWN_EXPORT_COLUMNS.map((column) => column.value(record)),
  );
  return [header, ...rows]
    .map((row) => row.map((cell) => csvCell(cell)).join(","))
    .join("\n");
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function fileSafeName(label: string): string {
  const safe = label.replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
  return safe || "daily_report_investigation";
}

function downloadCsv(records: DailyReportLiveRecord[], filename: string) {
  const blob = new Blob([recordsToCsv(records)], {
    type: "text/csv;charset=utf-8;",
  });
  downloadBlob(blob, filename);
}

async function downloadExcel(
  records: DailyReportLiveRecord[],
  filename: string,
  title: string,
) {
  const ExcelJS = (await import("exceljs")).default;
  const workbook = new ExcelJS.Workbook();
  workbook.creator = "Daily Report Investigation";
  const sheet = workbook.addWorksheet("Investigation");

  sheet.columns = DRILLDOWN_EXPORT_COLUMNS.map((column) => ({
    header: column.label,
    key: column.label,
    width: column.label === "Summary" ? 48 : column.label === "Group" ? 28 : 16,
  }));

  records.forEach((record) => {
    const rowData = DRILLDOWN_EXPORT_COLUMNS.reduce(
      (acc, column) => {
        acc[column.label] = column.value(record);
        return acc;
      },
      {} as Record<string, string | number>,
    );
    sheet.addRow(rowData);
  });

  sheet.insertRow(1, [title]);
  sheet.mergeCells(1, 1, 1, DRILLDOWN_EXPORT_COLUMNS.length);
  sheet.getCell(1, 1).font = { bold: true, size: 13 };
  sheet.getCell(1, 1).alignment = { vertical: "middle" };
  sheet.getRow(2).eachCell((cell) => {
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE60000" } };
    cell.font = { color: { argb: "FFFFFFFF" }, bold: true };
  });
  sheet.views = [{ state: "frozen", ySplit: 2 }];

  const buffer = await workbook.xlsx.writeBuffer();
  downloadBlob(
    new Blob([buffer], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }),
    filename,
  );
}

async function downloadPdf(
  records: DailyReportLiveRecord[],
  filename: string,
  title: string,
) {
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });

  doc.setFontSize(14);
  doc.setTextColor(26, 26, 26);
  doc.text(title, 36, 32);
  doc.setFontSize(9);
  doc.setTextColor(102, 102, 102);
  doc.text(
    `${records.length.toLocaleString("en-ZA")} records exported - ${new Date().toLocaleString("en-ZA")}`,
    36,
    48,
  );

  autoTable(doc, {
    startY: 62,
    margin: { left: 28, right: 28 },
    head: [DRILLDOWN_EXPORT_COLUMNS.map((column) => column.label)],
    body: records.map((record) =>
      DRILLDOWN_EXPORT_COLUMNS.map((column) => String(column.value(record))),
    ),
    styles: { fontSize: 7, cellPadding: 4, overflow: "linebreak" },
    headStyles: { fillColor: [230, 0, 0], textColor: 255, fontStyle: "bold" },
    alternateRowStyles: { fillColor: [250, 250, 250] },
  });

  doc.save(filename);
}

function selectionLabel(selection: DrilldownSelection): string {
  const parts = [selection.division, selection.assignee_group];
  if (selection.sla === "BREACHED") parts.push("Breached Calls");
  else if (selection.sla === "NEARING_SLA") parts.push("Calls Nearing SLA");
  if (selection.category) parts.push(selection.category);
  const joined = parts.filter(Boolean).join(" \u00b7 ");
  return joined || selection.title;
}

function RecordCard({ record }: { record: DailyReportLiveRecord }) {
  return (
    <div className="px-4 py-3 border-b border-[#F0F0F0] hover:bg-[#FAFAFA]">
      <div className="flex items-center gap-2 mb-1.5">
        <SlaBadge status={record.sla_status} />
        <CategoryChip category={record.report_category} />
        <PriorityChip priority={record.priority} />
        <span className="ml-auto text-[13px] font-700 text-[#1A1A1A] whitespace-nowrap">
          {fmtHours(record.hours_open)}
        </span>
      </div>
      <div className="flex items-center gap-1.5 text-[11px] font-mono text-[#5C5C5C] mb-1">
        <span className="text-[#0057A8]">{record.request_id}</span>
        {record.task_id && <span className="text-[#BCBCBC]">&middot;</span>}
        {record.task_id && <span>{record.task_id}</span>}
      </div>
      <p className="text-[12.5px] text-[#1A1A1A] leading-snug mb-1.5">
        {record.summary ?? "No summary provided"}
      </p>
      <div className="text-[10.5px] text-[#8C8C8C]">
        {record.assignee ?? "Unassigned"}
        {record.assignee_group && ` \u00b7 ${record.assignee_group}`}
        {record.scheduled_end && ` \u00b7 scheduled ${record.scheduled_end}`}
      </div>
    </div>
  );
}

function DrilldownPanel({
  selection,
  records,
  loading,
  onClose,
  onRefine,
}: {
  selection: DrilldownSelection;
  records: DailyReportLiveRecord[];
  loading: boolean;
  onClose: () => void;
  onRefine: (
    patch: Partial<Pick<DrilldownSelection, "sla" | "category">>,
  ) => void;
}) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("hours_desc");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("csv");
  const [visibleCount, setVisibleCount] = useState(100);

  // Reset local view state whenever the scope of the investigation changes,
  // so an old search/paged-in count doesn't silently carry over.
  useEffect(() => {
    setVisibleCount(100);
    setSearch("");
  }, [
    selection.division,
    selection.assignee_group,
    selection.sla,
    selection.category,
  ]);

  const filtered = records.filter((record) => matchesSearch(record, search));
  const sorted = sortRecords(filtered, sortKey);
  const shownRecords = sorted.slice(0, visibleCount);
  const hasMore = sorted.length > shownRecords.length;
  const exportTitle = `Daily Report Investigation - ${selectionLabel(selection)}`;
  const exportName = fileSafeName(selectionLabel(selection));

  async function exportInvestigation() {
    if (exportFormat === "csv") {
      downloadCsv(sorted, `${exportName}.csv`);
      return;
    }
    if (exportFormat === "excel") {
      await downloadExcel(sorted, `${exportName}.xlsx`, exportTitle);
      return;
    }
    await downloadPdf(sorted, `${exportName}.pdf`, exportTitle);
  }

  const slaChips: { label: string; value?: SlaStatus }[] = [
    { label: "All statuses", value: undefined },
    { label: "Breached", value: "BREACHED" },
    { label: "Nearing SLA", value: "NEARING_SLA" },
  ];

  const categoryChips: { label: string; value?: Category }[] = [
    { label: "All categories", value: undefined },
    { label: "Incident", value: "INCIDENT" },
    { label: "Change", value: "CHANGE" },
    { label: "Access", value: "ACCESS" },
    { label: "Event", value: "EVENT" },
  ];

  return (
    <div
      className="fixed inset-0 z-[80] flex justify-end bg-black/25"
      onClick={onClose}
    >
      <motion.aside
        initial={{ x: 640 }}
        animate={{ x: 0 }}
        exit={{ x: 640 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
        onClick={(event) => event.stopPropagation()}
        className="h-full w-[640px] max-w-[96vw] bg-white border-l border-[#D0D0D0] shadow-[0_0_30px_rgba(0,0,0,0.18)] flex flex-col"
      >
        <div className="px-4 py-3 border-b border-[#E5E5E5] flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-[0.6px] font-700 text-[#8C8C8C] mb-1">
              Investigation
            </div>
            <h2 className="text-[15px] font-700 text-[#1A1A1A] leading-tight">
              {selectionLabel(selection)}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[#8C8C8C] hover:text-[#1A1A1A] rounded flex-shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        {/* Refine without closing: these chips re-trigger the same query the
            parent already runs for a clicked cell, just with a new sla/category. */}
        <div className="px-4 py-2.5 border-b border-[#E5E5E5] bg-[#FAFAFA] space-y-1.5">
          <div className="flex flex-wrap gap-1.5">
            {slaChips.map((chip) => (
              <button
                key={chip.label}
                type="button"
                onClick={() => onRefine({ sla: chip.value })}
                className={cn(
                  "px-2.5 py-1 rounded-full text-[11px] font-600 border transition-colors",
                  selection.sla === chip.value
                    ? "bg-[#1A1A1A] text-white border-[#1A1A1A]"
                    : "bg-white text-[#5C5C5C] border-[#D0D0D0] hover:border-[#1A1A1A]",
                )}
              >
                {chip.label}
              </button>
            ))}
            <div className="w-px bg-[#E5E5E5] mx-0.5" />
            {categoryChips.map((chip) => (
              <button
                key={chip.label}
                type="button"
                onClick={() => onRefine({ category: chip.value })}
                className={cn(
                  "px-2.5 py-1 rounded-full text-[11px] font-600 border transition-colors",
                  selection.category === chip.value
                    ? "bg-[#1A1A1A] text-white border-[#1A1A1A]"
                    : "bg-white text-[#5C5C5C] border-[#D0D0D0] hover:border-[#1A1A1A]",
                )}
              >
                {chip.label}
              </button>
            ))}
          </div>
          {(selection.division || selection.assignee_group) && (
            <div className="flex flex-wrap gap-1.5 pt-0.5">
              {selection.division && (
                <Tag variant="info">{selection.division}</Tag>
              )}
              {selection.assignee_group && (
                <Tag variant="success">{selection.assignee_group}</Tag>
              )}
            </div>
          )}
        </div>

        <div className="px-4 py-2.5 border-b border-[#E5E5E5] flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search request, task, assignee, summary..."
            className="flex-1 h-8 px-2.5 text-[12px] border border-[#D0D0D0] rounded-md outline-none focus:border-[#E60000] min-w-0"
          />
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="h-8 px-2 text-[12px] border border-[#D0D0D0] rounded-md bg-white outline-none focus:border-[#E60000] flex-shrink-0"
          >
            {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => (
              <option key={key} value={key}>
                {SORT_LABEL[key]}
              </option>
            ))}
          </select>
          <select
            value={exportFormat}
            onChange={(e) => setExportFormat(e.target.value as ExportFormat)}
            className="h-8 px-2 text-[12px] border border-[#D0D0D0] rounded-md bg-white outline-none focus:border-[#E60000] flex-shrink-0"
            title="Export format"
          >
            {(Object.keys(EXPORT_LABEL) as ExportFormat[]).map((format) => (
              <option key={format} value={format}>
                {EXPORT_LABEL[format]}
              </option>
            ))}
          </select>
          <Btn
            variant="default"
            size="sm"
            onClick={() => void exportInvestigation()}
            disabled={!sorted.length}
          >
            <Download size={11} /> Export
          </Btn>
        </div>

        <div className="px-4 py-2 border-b border-[#E5E5E5] text-[11px] text-[#8C8C8C] flex items-center gap-1.5">
          {loading ? (
            "Loading records..."
          ) : (
            <>
              <span className="font-600 text-[#1A1A1A]">
                {sorted.length.toLocaleString("en-ZA")}
              </span>
              {sorted.length !== records.length && (
                <span>of {records.length.toLocaleString("en-ZA")}</span>
              )}
              <span>matching records</span>
            </>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 space-y-2">
              {[1, 2, 3, 4, 5].map((item) => (
                <div key={item} className="h-20 skeleton rounded-md" />
              ))}
            </div>
          ) : !shownRecords.length ? (
            <EmptyState
              title="No matching records"
              sub={
                search
                  ? "No records match your search. Try a different term or clear it."
                  : "The backend returned no drill-through records for this selection."
              }
            />
          ) : (
            <>
              {shownRecords.map((record) => (
                <RecordCard
                  key={`${record.request_id}-${record.task_id}`}
                  record={record}
                />
              ))}
              {hasMore && (
                <div className="p-4 text-center">
                  <Btn
                    variant="default"
                    size="sm"
                    onClick={() => setVisibleCount((count) => count + 100)}
                  >
                    Load {Math.min(100, sorted.length - shownRecords.length)}{" "}
                    more
                  </Btn>
                </div>
              )}
            </>
          )}
        </div>
      </motion.aside>
    </div>
  );
}

function DivisionBlock({
  division,
  groupMatrix,
  index,
  onOpenDrilldown,
}: {
  division: string;
  groupMatrix: GroupMatrix;
  index: number;
  onOpenDrilldown: (selection: DrilldownSelection) => void;
}) {
  const groups = Object.keys(groupMatrix).sort((a, b) => a.localeCompare(b));
  const divTotals: Record<Band, GroupBandRow> = {
    "Total Open Calls": {
      incident: 0,
      change: 0,
      access: 0,
      event: 0,
      total: 0,
    },
    "Calls Nearing SLA": {
      incident: 0,
      change: 0,
      access: 0,
      event: 0,
      total: 0,
    },
    "Breached Calls": { incident: 0, change: 0, access: 0, event: 0, total: 0 },
    "Closed Successfully Yesterday": { incident: 0, change: 0, access: 0, event: 0, total: 0 },
  };

  groups.forEach((group) => {
    SLA_BANDS.forEach((band) => {
      const row = groupMatrix[group][band];
      if (!row) return;
      divTotals[band].incident += row.incident;
      divTotals[band].change += row.change;
      divTotals[band].access += row.access;
      divTotals[band].event += row.event;
      divTotals[band].total += row.total;
    });
  });

  const totalOpen = divTotals["Total Open Calls"].total;
  const totalBreached = divTotals["Breached Calls"].total;
  const totalNearing = divTotals["Calls Nearing SLA"].total;

  function openDrilldown(
    band: Band,
    categoryKey?: keyof GroupBandRow,
    group?: string,
  ) {
    const category = categoryKey ? CATEGORY_BY_COLUMN[categoryKey] : undefined;
    const scopeParts = [division, group, band, category].filter(Boolean);

    onOpenDrilldown({
      title: scopeParts.join(" - "),
      division,
      assignee_group: group,
      sla: slaForBand(band),
      category,
    });
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="bg-white border border-[#E5E5E5] rounded-lg overflow-hidden"
    >
      <div className="flex items-center gap-3 px-4 py-2.5 bg-[#FAFAFA] border-b border-[#E5E5E5]">
        <span className="text-[13px] font-700 text-[#1A1A1A] min-w-[48px]">
          {division}
        </span>
        <div className="flex items-center gap-2 ml-1">
          {totalBreached > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-px bg-[#FFF0F0] border border-[#F5B8B8] text-[#CC0000] text-[10px] font-600 rounded">
              <AlertTriangle size={9} /> {totalBreached} breached
            </span>
          )}
          {totalNearing > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-px bg-[#FFF8E6] border border-[#F5D580] text-[#C47000] text-[10px] font-600 rounded">
              <Clock size={9} /> {totalNearing} nearing
            </span>
          )}
        </div>
        <span className="ml-auto text-[11px] text-[#8C8C8C]">
          {totalOpen} total open
        </span>
      </div>

      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="text-left text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.5px] py-2 px-3 bg-[#FAFAFA] border-b border-[#E5E5E5] w-[180px]">
              Group
            </th>
            <th className="text-left text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.5px] py-2 px-3 bg-[#FAFAFA] border-b border-[#E5E5E5] w-[130px]">
              Status
            </th>
            {["Incident", "Change", "Access", "Event", "Total"].map((label) => (
              <th
                key={label}
                className={cn(
                  "text-right text-[10px] font-600 uppercase tracking-[0.5px] py-2 px-3 bg-[#FAFAFA] border-b border-[#E5E5E5]",
                  label === "Total" ? "text-[#1A1A1A]" : "text-[#8C8C8C]",
                )}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group, groupIndex) => (
            <Fragment key={group}>
              {SLA_BANDS.map((band, bandIndex) => {
                const row = groupMatrix[group][band];
                const style = BAND_STYLE[band];
                const isFirstBand = bandIndex === 0;
                const isLastBand = bandIndex === SLA_BANDS.length - 1;
                const isLastGroup = groupIndex === groups.length - 1;

                return (
                  <tr
                    key={`${group}-${band}`}
                    className={cn(
                      "transition-colors",
                      style.rowBg,
                      !isLastBand || !isLastGroup
                        ? "border-b border-[#F0F0F0]"
                        : "",
                      isLastBand && !isLastGroup
                        ? "border-b-2 border-b-[#E5E5E5]"
                        : "",
                    )}
                  >
                    {isFirstBand && (
                      <td
                        rowSpan={SLA_BANDS.length}
                        className="px-3 py-2 text-[11px] font-500 text-[#1A1A1A] align-middle border-r border-[#F0F0F0] bg-white"
                        title={group}
                      >
                        {shortGroupLabel(group)}
                      </td>
                    )}
                    <td className="px-3 py-1.5">
                      <span
                        className={cn(
                          "inline-flex items-center px-2 py-[3px] rounded text-[10px] font-600",
                          style.labelBg,
                          style.labelText,
                        )}
                      >
                        {style.label}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right text-[12px]">
                      <ClickableVal
                        v={row?.incident ?? 0}
                        band={band}
                        onClick={() => openDrilldown(band, "incident", group)}
                      />
                    </td>
                    <td className="px-3 py-1.5 text-right text-[12px]">
                      <ClickableVal
                        v={row?.change ?? 0}
                        band={band}
                        onClick={() => openDrilldown(band, "change", group)}
                      />
                    </td>
                    <td className="px-3 py-1.5 text-right text-[12px]">
                      <ClickableVal
                        v={row?.access ?? 0}
                        band={band}
                        onClick={() => openDrilldown(band, "access", group)}
                      />
                    </td>
                    <td className="px-3 py-1.5 text-right text-[12px]">
                      <ClickableVal
                        v={row?.event ?? 0}
                        band={band}
                        onClick={() => openDrilldown(band, "event", group)}
                      />
                    </td>
                    <td
                      className={cn(
                        "px-3 py-1.5 text-right text-[12px] font-700 border-l border-[#F0F0F0]",
                        style.totalText,
                      )}
                    >
                      <ClickableVal
                        v={row?.total ?? 0}
                        band={band}
                        onClick={() => openDrilldown(band, "total", group)}
                      />
                    </td>
                  </tr>
                );
              })}
            </Fragment>
          ))}
          <tr className="border-t-2 border-[#E5E5E5] bg-[#FAFAFA]">
            <td
              colSpan={2}
              className="px-3 py-2 text-[10px] font-700 text-[#5C5C5C] uppercase tracking-[0.5px]"
            >
              {division} Total Open
            </td>
            <td className="px-3 py-2 text-right text-[12px] font-700 text-[#1A1A1A]">
              <ClickableVal
                v={divTotals["Total Open Calls"].incident}
                band="Total Open Calls"
                onClick={() => openDrilldown("Total Open Calls", "incident")}
              />
            </td>
            <td className="px-3 py-2 text-right text-[12px] font-700 text-[#1A1A1A]">
              <ClickableVal
                v={divTotals["Total Open Calls"].change}
                band="Total Open Calls"
                onClick={() => openDrilldown("Total Open Calls", "change")}
              />
            </td>
            <td className="px-3 py-2 text-right text-[12px] font-700 text-[#1A1A1A]">
              <ClickableVal
                v={divTotals["Total Open Calls"].access}
                band="Total Open Calls"
                onClick={() => openDrilldown("Total Open Calls", "access")}
              />
            </td>
            <td className="px-3 py-2 text-right text-[12px] font-700 text-[#1A1A1A]">
              <ClickableVal
                v={divTotals["Total Open Calls"].event}
                band="Total Open Calls"
                onClick={() => openDrilldown("Total Open Calls", "event")}
              />
            </td>
            <td className="px-3 py-2 text-right text-[13px] font-700 text-[#1A1A1A] border-l border-[#E5E5E5]">
              <ClickableVal
                v={divTotals["Total Open Calls"].total}
                band="Total Open Calls"
                onClick={() => openDrilldown("Total Open Calls", "total")}
              />
            </td>
          </tr>
        </tbody>
      </table>
    </motion.div>
  );
}

export default function DailyReportPage() {
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const report = reportFromPath(pathname);
  const [assigneeGroup, setAssigneeGroup] = useState("");
  const [drilldown, setDrilldown] = useState<DrilldownSelection | null>(null);
  const [showClosureBreakdown, setShowClosureBreakdown] = useState(false);
  const { reportDate: selectedReportDate, setReportDate } = useReportDate();
  const selectedDivision = report.division;
  const period = "day";

  const includeRecords = false;

  const {
    data: reportView,
    isLoading,
    refetch: refetchReport,
  } = useQuery({
    queryKey: [
      "daily-report-view",
      selectedReportDate,
      selectedDivision,
      assigneeGroup,
      includeRecords,
    ],
    queryFn: () =>
      dailyReportApi.view({
        date: selectedReportDate,
        period,
        division: selectedDivision,
        assignee_group: assigneeGroup || undefined,
        include_dates: true,
        include_records: includeRecords,
      }),
    refetchInterval: 120_000,
  });

  const { data: drilldownData, isFetching: isDrilldownLoading } = useQuery({
    queryKey: ["daily-report-drilldown", selectedReportDate, drilldown],
    queryFn: () =>
      dailyReportApi.records({
        date: selectedReportDate,
        period,
        division: drilldown?.division,
        assignee_group: drilldown?.assignee_group,
        sla: drilldown?.sla ?? "",
        category: drilldown?.category ?? "",
      }),
    enabled: !!drilldown,
  });

  const dataAvailable = reportView?.data_available !== false;
  const kpis = dataAvailable ? reportView?.kpis : undefined;
  const summaryRows = dataAvailable ? (reportView?.summary.rows ?? []) : [];
  const groups = dataAvailable ? (reportView?.groups ?? []) : [];
  const selectedDateRecords =
    dataAvailable
      ? (reportView?.records?.records ?? [])
      : [];
  const needsRecordGroupFallback = Boolean(
    includeRecords &&
    selectedDateRecords.length &&
    !hasSummaryGroupBreakdown(summaryRows, selectedDivision),
  );
  const reportTotals = totalsFromKpis(kpis);
  const reportDate = reportView?.report_date ?? kpis?.report_date;
  const closureBreakdown = (kpis?.successful_closures_by_group ?? []).filter(
    row => (!selectedDivision || row.division === selectedDivision)
      && (!assigneeGroup || row.assignee_group === assigneeGroup),
  );
  const closureDate = closureBreakdown[0]?.closure_date;
  const dateRangeLabel = reportDate
    ? fmtDate(reportDate, "EEEE, dd MMMM yyyy")
    : "Today";
  const dailyGroup = groups.find(
    (group) => group.report_group === selectedDivision,
  );
  const assigneeGroups = selectedDivision
    ? (dailyGroup?.assignee_groups ?? [])
    : [];
  const matrix = needsRecordGroupFallback
    ? buildLiveMatrix(selectedDateRecords, selectedDivision, assigneeGroups)
    : addClosureFallback(
        buildMatrix(summaryRows, selectedDivision, assigneeGroups),
        closureBreakdown,
      );
  const divisions = Object.keys(matrix).sort();
  const subtitle = `Daily view - ${dateRangeLabel} - ${selectedDivision ?? "all configured divisions"}${assigneeGroup ? ` - ${assigneeGroup}` : ""}`;

  useEffect(() => {
    setDrilldown(null);
    setShowClosureBreakdown(false);
  }, [selectedReportDate]);

  useEffect(() => {
    if (!reportView || reportView.data_available || reportView.is_historical) return;

    queryClient.removeQueries({ queryKey: ["daily-report-drilldown"] });
    queryClient.removeQueries({
      predicate: query => query.queryKey[0] === "daily-report-view"
        && query.queryKey[1] !== selectedReportDate,
    });
  }, [queryClient, reportView, selectedReportDate]);

  function openReportDrilldown(
    selection: Omit<DrilldownSelection, "division"> & { division?: string },
  ) {
    setDrilldown({
      division: selectedDivision,
      ...selection,
    });
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <PageHeader
        breadcrumb={["Reports", report.navLabel]}
        title={report.title}
        subtitle={subtitle}
        actions={
          <>
            <select
              aria-label="Report snapshot date"
              value={selectedReportDate}
              onChange={event => setReportDate(event.target.value)}
              className="h-7 rounded-md border border-[#D0D0D0] bg-white px-2 text-[11px] text-[#1A1A1A] outline-none focus:border-[#E60000]"
            >
              {!reportView?.available_dates?.dates.some(date => date.report_date === selectedReportDate) && (
                <option value={selectedReportDate}>{fmtDate(selectedReportDate, "dd MMMM yyyy")}</option>
              )}
              {reportView?.available_dates?.dates.map(date => (
                <option key={date.report_date} value={date.report_date}>
                  {fmtDate(date.report_date, "dd MMMM yyyy")}
                </option>
              ))}
            </select>
            <Btn variant="default" size="sm" onClick={() => window.print()}>
              <Printer size={11} /> Print
            </Btn>
            <Btn variant="default" size="sm" onClick={() => refetchReport()}>
              <RefreshCw size={11} /> Refresh
            </Btn>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {!isLoading && reportView?.data_available === false ? (
          <div className="bg-white border border-[#E5E5E5] rounded-lg">
            <EmptyState
              title={reportView.is_historical
                ? `No report data has been loaded for ${fmtDate(reportView.report_date, "dd MMMM yyyy")}.`
                : "No report data has been loaded for today."}
              sub={reportView.is_historical
                ? "Choose another available historical snapshot."
                : `Historical reports are available only when you manually select a date. Timezone: ${reportView.timezone}.`}
            />
          </div>
        ) : (<>
        <div className="grid grid-cols-5 gap-3">
          {[
            {
              label: "Total Open",
              value: reportTotals.total,
              variant: "default",
              icon: <Activity size={36} />,
            },
            {
              label: "Breached",
              value: reportTotals.breached,
              variant: "danger",
              icon: <AlertTriangle size={36} />,
            },
            {
              label: "Nearing SLA",
              value: reportTotals.nearing,
              variant: "warning",
              icon: <Clock size={36} />,
            },
            {
              label: "Within SLA",
              value: reportTotals.within,
              variant: "success",
              icon: <CheckCircle2 size={36} />,
            },
            {
              label: "Closed Successfully Yesterday",
              value: reportTotals.closedSuccessfullyYesterday,
              variant: "teal",
              sub: closureDate
                ? `Closed on ${fmtDate(closureDate, "dd MMMM yyyy")}`
                : "No successful closures",
              icon: <CheckCircle2 size={36} />,
            },
          ].map((item, index) => (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.07 }}
            >
              <KpiCard
                label={item.label}
                value={item.value}
                variant={
                  item.variant as "danger" | "warning" | "success" | "teal" | "info" | "default"
                }
                icon={item.icon}
                sub={item.sub}
                loading={isLoading}
                onClick={
                  item.value > 0
                    ? () => {
                        if (item.label === "Closed Successfully Yesterday") {
                          setShowClosureBreakdown(current => !current);
                        } else if (item.label === "Breached") {
                          openReportDrilldown({
                            title: `${report.navLabel} - Breached Calls`,
                            sla: "BREACHED",
                          });
                        } else if (item.label === "Nearing SLA") {
                          openReportDrilldown({
                            title: `${report.navLabel} - Calls Nearing SLA`,
                            sla: "NEARING_SLA",
                          });
                        } else if (item.label === "Within SLA") {
                          openReportDrilldown({
                            title: `${report.navLabel} - Within SLA`,
                            sla: "WITHIN_SLA",
                          });
                        } else if (item.label === "Total Open") {
                          openReportDrilldown({
                            title: `${report.navLabel} - Total Open`,
                          });
                        }
                      }
                    : undefined
                }
              />
            </motion.div>
          ))}
        </div>

        {showClosureBreakdown && (
          <div className="bg-white border border-[#E5E5E5] rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-[#E5E5E5]">
              <h2 className="text-[12px] font-600 text-[#1A1A1A]">Closed Successfully Yesterday by group</h2>
              <p className="text-[10px] text-[#8C8C8C] mt-0.5">Historical closures only; these counts are excluded from open and SLA totals.</p>
            </div>
            {closureBreakdown.length ? (
              <table className="w-full border-collapse">
                <thead><tr>{["Division", "Assignee Group", "Closure Date", "Successfully Closed Count"].map(label => (
                  <th key={label} className="px-4 py-2 text-left text-[9px] font-600 uppercase tracking-wide text-[#8C8C8C] bg-[#FAFAFA] border-b border-[#E5E5E5] last:text-right">{label}</th>
                ))}</tr></thead>
                <tbody>{closureBreakdown.map(row => (
                  <tr key={`${row.division}-${row.assignee_group}-${row.closure_date}`} className="border-b border-[#F0F0F0] last:border-0">
                    <td className="px-4 py-2.5 text-[11px]">{row.division}</td>
                    <td className="px-4 py-2.5 text-[11px]">{row.assignee_group}</td>
                    <td className="px-4 py-2.5 text-[11px]">{fmtDate(row.closure_date, "dd MMMM yyyy")}</td>
                    <td className="px-4 py-2.5 text-[11px] text-right font-600 text-[#008577]">{row.total_closed_success.toLocaleString("en-ZA")}</td>
                  </tr>
                ))}</tbody>
              </table>
            ) : (
              <EmptyState title="No successful closures" sub="There were no successful closures for the active division and assignee group filters." icon={<CheckCircle2 size={30} />} />
            )}
          </div>
        )}

        {!!divisions.length && (
          <div className="bg-white border border-[#E5E5E5] rounded-lg px-4 py-3 flex items-center gap-6">
            <span className="text-[11px] font-600 text-[#5C5C5C] uppercase tracking-wide">
              Category split
            </span>
            {[
              {
                label: "Incidents",
                value: reportTotals.incidents,
                color: "text-[#CC0000]",
                dot: "bg-[#E60000]",
              },
              {
                label: "Changes",
                value: reportTotals.changes,
                color: "text-[#0057A8]",
                dot: "bg-[#0057A8]",
              },
              {
                label: "Access",
                value: reportTotals.access,
                color: "text-[#6B21A8]",
                dot: "bg-[#6B21A8]",
              },
              {
                label: "Events",
                value: reportTotals.events,
                color: "text-[#C47000]",
                dot: "bg-[#F59E0B]",
              },
            ].map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={() => {
                  const category =
                    item.label === "Incidents"
                      ? "INCIDENT"
                      : item.label === "Changes"
                        ? "CHANGE"
                        : item.label === "Access"
                          ? "ACCESS"
                          : "EVENT";
                  openReportDrilldown({
                    title: `${report.navLabel} - ${item.label}`,
                    category,
                  });
                }}
                disabled={!item.value}
                className="flex items-center gap-2 rounded px-1.5 py-1 text-left disabled:cursor-default disabled:opacity-60 hover:bg-[#F5F5F5]"
              >
                <div
                  className={cn(
                    "w-2 h-2 rounded-[2px] flex-shrink-0",
                    item.dot,
                  )}
                />
                <span className="text-[12px] text-[#5C5C5C]">{item.label}</span>
                <span className={cn("text-[14px] font-700", item.color)}>
                  {item.value}
                </span>
              </button>
            ))}
            <div className="ml-auto flex items-center gap-2">
              <div className="w-px h-5 bg-[#E5E5E5]" />
              <span className="text-[12px] text-[#5C5C5C]">
                {report.navLabel} Total Open
              </span>
              <span className="text-[16px] font-700 text-[#1A1A1A]">
                {reportTotals.total}
              </span>
            </div>
          </div>
        )}

        {selectedDivision && (
          <div className="bg-white border border-[#E5E5E5] rounded-lg px-4 py-3 flex items-center gap-3">
            <span className="text-[11px] font-600 text-[#5C5C5C] uppercase tracking-wide">
              Assignee group
            </span>
            <select
              value={assigneeGroup}
              onChange={(e) => setAssigneeGroup(e.target.value)}
              className="h-8 px-2 text-[12px] border border-[#D0D0D0] rounded-md bg-white outline-none focus:border-[#E60000] min-w-[260px]"
            >
              <option value="">All groups</option>
              {assigneeGroups.map((group) => (
                <option key={group} value={group}>
                  {group}
                </option>
              ))}
            </select>
            {!!dailyGroup && (
              <span className="text-[11px] text-[#8C8C8C] ml-auto">
                {dailyGroup.active_records} active records across{" "}
                {dailyGroup.assignee_group_count ?? assigneeGroups.length}{" "}
                groups
              </span>
            )}
          </div>
        )}

        <div className="flex items-center gap-2">
          <h2 className="text-[13px] font-600 text-[#1A1A1A]">
            Daily Report Breakdown
          </h2>
          <span className="text-[11px] text-[#8C8C8C]">
            - grouped by division groups and service category
          </span>
          {reportTotals.breached > 0 && (
            <Tag variant="danger">
              {reportTotals.breached} breached in {report.navLabel}
            </Tag>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-48 skeleton rounded-lg" />
            ))}
          </div>
        ) : !divisions.length ? (
          <EmptyState
            title="No report data found"
            sub={`No daily report rows were returned for ${selectedDivision ?? "all divisions"} on ${dateRangeLabel}.`}
          />
        ) : (
          <div className="space-y-4">
            {divisions.map((division, index) => (
              <DivisionBlock
                key={division}
                division={division}
                groupMatrix={matrix[division]}
                index={index}
                onOpenDrilldown={setDrilldown}
              />
            ))}
          </div>
        )}
        </>)}
      </div>

      {drilldown && (
        <DrilldownPanel
          selection={drilldown}
          records={drilldownData?.records ?? []}
          loading={isDrilldownLoading}
          onClose={() => setDrilldown(null)}
          onRefine={(patch) =>
            setDrilldown((prev) => (prev ? { ...prev, ...patch } : prev))
          }
        />
      )}
    </div>
  );
}
