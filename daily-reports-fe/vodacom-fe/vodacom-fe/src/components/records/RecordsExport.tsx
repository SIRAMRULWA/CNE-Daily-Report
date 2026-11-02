'use client'

import { FileSpreadsheet, FileText } from 'lucide-react'
import { Btn } from '@/components/ui'
import type { WorkspaceRecord, SlaStatus } from '@/types'

function fileDate() {
  return new Date().toISOString().slice(0, 10)
}

const EXPORT_COLUMNS: { key: keyof WorkspaceRecord; label: string }[] = [
  { key: 'sla_status', label: 'SLA' },
  { key: 'request_id', label: 'Request ID' },
  { key: 'task_id', label: 'Task ID' },
  { key: 'division', label: 'Division' },
  { key: 'assignee_group', label: 'Group' },
  { key: 'report_category', label: 'Category' },
  { key: 'priority', label: 'Priority' },
  { key: 'status', label: 'Status' },
  { key: 'status_reason', label: 'Status Reason' },
  { key: 'assignee', label: 'Assignee' },
  { key: 'summary', label: 'Summary' },
  { key: 'hours_open', label: 'Hours Open' },
  { key: 'due_at', label: 'Due At' },
  { key: 'assign_time', label: 'Assign Time' },
  { key: 'closed_time', label: 'Closed Time' },
]

// Matches the SLA_CHIPS palette used in RecordsPage
const SLA_COLORS: Record<SlaStatus, { bg: string; text: string; pdf: [number, number, number] }> = {
  BREACHED:    { bg: 'FFF0F0', text: 'CC0000', pdf: [255, 240, 240] },
  NEARING_SLA: { bg: 'FFF8E6', text: 'C47000', pdf: [255, 248, 230] },
  NO_SCHEDULE: { bg: 'EEF4FF', text: '0057A8', pdf: [238, 244, 255] },
  WITHIN_SLA:  { bg: 'EDF7ED', text: '0A7A0A', pdf: [237, 247, 237] },
  CLOSED:      { bg: 'F0F0F0', text: '5C5C5C', pdf: [240, 240, 240] },
}

const HEADER_RED = 'E60000'

export function RecordsExport({ records, disabled }: { records: WorkspaceRecord[]; disabled?: boolean }) {
  async function exportExcel() {
    const ExcelJS = (await import('exceljs')).default

    const workbook = new ExcelJS.Workbook()
    workbook.creator = 'Operations Records'
    const sheet = workbook.addWorksheet('Operations Records')

    sheet.columns = EXPORT_COLUMNS.map(col => ({
      header: col.label,
      key: col.key as string,
      width: col.key === 'summary' ? 40 : col.key === 'assignee_group' ? 22 : 16,
    }))

    records.forEach(record => {
      const rowData = EXPORT_COLUMNS.reduce((acc, col) => {
        acc[col.key as string] = record[col.key] ?? ''
        return acc
      }, {} as Record<string, unknown>)
      const row = sheet.addRow(rowData)

      const colors = record.sla_status ? SLA_COLORS[record.sla_status as SlaStatus] : undefined
      if (colors) {
        row.eachCell(cell => {
          cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${colors.bg}` } }
        })
        const slaCell = row.getCell('sla_status')
        slaCell.font = { color: { argb: `FF${colors.text}` }, bold: true }
      }
    })

    // Header styling
    sheet.getRow(1).eachCell(cell => {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: `FF${HEADER_RED}` } }
      cell.font = { color: { argb: 'FFFFFFFF' }, bold: true }
    })
    sheet.views = [{ state: 'frozen', ySplit: 1 }]

    const buffer = await workbook.xlsx.writeBuffer()
    const blob = new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `operations-records-${fileDate()}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
  }

  async function exportPdf() {
    const { default: jsPDF } = await import('jspdf')
    const { default: autoTable } = await import('jspdf-autotable')

    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' })

    doc.setFontSize(14)
    doc.setTextColor(26, 26, 26)
    doc.text('Operations Records', 40, 32)

    doc.setFontSize(9)
    doc.setTextColor(102, 102, 102)
    doc.text(
      `${records.length} records exported  —  ${new Date().toLocaleString('en-ZA')}`,
      40,
      46,
    )

    autoTable(doc, {
      startY: 58,
      margin: { left: 30, right: 30 },
      head: [EXPORT_COLUMNS.map(c => c.label)],
      body: records.map(record => EXPORT_COLUMNS.map(col => String(record[col.key] ?? ''))),
      styles: { fontSize: 7, cellPadding: 4, overflow: 'linebreak' },
      headStyles: { fillColor: [230, 0, 0], textColor: 255, fontStyle: 'bold' },
      alternateRowStyles: { fillColor: [250, 250, 250] },
      didParseCell: data => {
        if (data.section !== 'body') return
        const record = records[data.row.index]
        const colors = record?.sla_status ? SLA_COLORS[record.sla_status as SlaStatus] : undefined
        if (colors) {
          data.cell.styles.fillColor = colors.pdf
          if (data.column.index === 0) {
            data.cell.styles.fontStyle = 'bold'
          }
        }
      },
    })

    doc.save(`operations-records-${fileDate()}.pdf`)
  }

  return (
    <div className="flex items-center gap-1.5">
      <Btn variant="default" size="sm" disabled={disabled || !records.length} onClick={exportPdf}>
        <FileText size={11} /> PDF
      </Btn>
      <Btn variant="default" size="sm" disabled={disabled || !records.length} onClick={exportExcel}>
        <FileSpreadsheet size={11} /> Excel
      </Btn>
    </div>
  )
}