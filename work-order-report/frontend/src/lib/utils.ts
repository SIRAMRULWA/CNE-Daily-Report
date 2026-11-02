import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { formatDistanceToNow, format, parseISO } from 'date-fns'
import type { SlaStatus, Category, Role } from '@/types'

// ─── Classnames ──────────────────────────────────────────────────────────────

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// ─── Formatters ──────────────────────────────────────────────────────────────

export function fmtDate(iso: string | null | undefined, fmt = 'dd MMM yyyy'): string {
  if (!iso) return '—'
  try { return format(parseISO(iso), fmt) } catch { return '—' }
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try { return format(parseISO(iso), 'dd MMM yyyy · HH:mm') } catch { return '—' }
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  try { return formatDistanceToNow(parseISO(iso), { addSuffix: true }) } catch { return '—' }
}

export function fmtHours(value: number | string | null | undefined): string {
  if (value == null || value === '') return '—'
  const hours = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(hours)) return '—'
  if (hours < 1) return `${Math.round(hours * 60)}m`
  return `${hours.toFixed(1)}h`
}

// ─── SLA countdown ───────────────────────────────────────────────────────────

export function fmtCountdown(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const abs = Math.abs(seconds)
  const h = Math.floor(abs / 3600)
  const m = Math.floor((abs % 3600) / 60)
  const s = abs % 60
  const sign = seconds < 0 ? '-' : '+'
  if (h > 0) return `${sign}${h}h ${String(m).padStart(2, '0')}m`
  return `${sign}${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`
}

// ─── SLA styling ─────────────────────────────────────────────────────────────

export const SLA_LABELS: Record<SlaStatus, string> = {
  BREACHED: 'Breached',
  NEARING_SLA: 'Nearing SLA',
  NO_SCHEDULE: 'No Schedule',
  WITHIN_SLA: 'Within SLA',
  CLOSED: 'Closed',
}

export const SLA_COLORS: Record<SlaStatus, { bg: string; text: string; border: string }> = {
  BREACHED:    { bg: 'bg-red-50',    text: 'text-red-700',    border: 'border-red-200' },
  NEARING_SLA: { bg: 'bg-amber-50',  text: 'text-amber-700',  border: 'border-amber-200' },
  NO_SCHEDULE: { bg: 'bg-blue-50',   text: 'text-blue-700',   border: 'border-blue-200' },
  WITHIN_SLA:  { bg: 'bg-green-50',  text: 'text-green-700',  border: 'border-green-200' },
  CLOSED:      { bg: 'bg-gray-100',  text: 'text-gray-500',   border: 'border-gray-200' },
}

export const CATEGORY_COLORS: Record<Category, { bg: string; text: string }> = {
  INCIDENT: { bg: 'bg-red-50',    text: 'text-red-700' },
  CHANGE:   { bg: 'bg-blue-50',   text: 'text-blue-700' },
  ACCESS:   { bg: 'bg-purple-50', text: 'text-purple-700' },
  EVENT:    { bg: 'bg-amber-50',  text: 'text-amber-700' },
}

export const DIVISION_COLORS: Record<string, string> = {
  INTSS: '#E60000',
  NSD:   '#0057A8',
  CVDI:  '#6B21A8',
  CDN:   '#0F766E',
}

export const ROLE_LABELS: Record<Role, string> = {
  SUPER_ADMIN: 'Super Admin',
  ADMIN:       'Admin',
  MANAGER:     'Manager',
  USER:        'User',
  READ_ONLY:   'Read Only',
}

// ─── Hours colouring ─────────────────────────────────────────────────────────

export function hoursColor(h: number | null | undefined, sla: SlaStatus | null | undefined): string {
  if (sla === 'BREACHED') return 'text-red-600 font-semibold'
  if (sla === 'NEARING_SLA') return 'text-amber-600 font-medium'
  if (h == null) return 'text-gray-400'
  if (h > 24) return 'text-red-500'
  if (h > 8) return 'text-amber-500'
  return 'text-gray-600'
}

// ─── Role checks ─────────────────────────────────────────────────────────────

// ─── SLA summary aggregation ─────────────────────────────────────────────────

export function aggregateSummaryRows(rows: { sla_status: SlaStatus; record_count: number }[]) {
  const totals = { BREACHED: 0, NEARING_SLA: 0, NO_SCHEDULE: 0, WITHIN_SLA: 0, CLOSED: 0, total: 0 }
  for (const r of rows) {
    totals[r.sla_status] = (totals[r.sla_status] ?? 0) + r.record_count
    totals.total += r.record_count
  }
  return totals
}
