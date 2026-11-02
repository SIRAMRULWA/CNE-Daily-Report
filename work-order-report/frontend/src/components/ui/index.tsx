import { cn, SLA_COLORS, SLA_LABELS, CATEGORY_COLORS } from '@/lib/utils'
import type { SlaStatus, Category } from '@/types'

// ─── SLA Badge ───────────────────────────────────────────────────────────────

export function SlaBadge({ status }: { status: SlaStatus | null | undefined }) {
  if (!status) return <span className="text-gray-400 text-[11px]">—</span>
  const c = SLA_COLORS[status]
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-[3px] rounded text-[10px] font-600 uppercase tracking-[0.4px] border whitespace-nowrap',
      c.bg, c.text, c.border
    )}>
      {SLA_LABELS[status]}
    </span>
  )
}

// ─── Category Chip ────────────────────────────────────────────────────────────

export function CategoryChip({ category }: { category: Category | null | undefined }) {
  if (!category) return null
  const c = CATEGORY_COLORS[category]
  return (
    <span className={cn(
      'inline-flex items-center px-1.5 py-[2px] rounded text-[10px] font-500',
      c.bg, c.text
    )}>
      {category}
    </span>
  )
}

// ─── Priority Chip ────────────────────────────────────────────────────────────

export function PriorityChip({ priority }: { priority: string | null | undefined }) {
  if (!priority) return <span className="text-gray-400 text-[11px]">—</span>
  const colors: Record<string, string> = {
    High: 'text-[#E60000]', Medium: 'text-[#C47000]', Low: 'text-[#0A7A0A]', Critical: 'text-[#9D0000]'
  }
  const dots: Record<string, string> = {
    High: 'bg-[#E60000]', Medium: 'bg-[#F59E0B]', Low: 'bg-[#16A34A]', Critical: 'bg-[#9D0000]'
  }
  const p = priority.charAt(0).toUpperCase() + priority.slice(1).toLowerCase()
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-[10px] font-500', colors[p] ?? 'text-[#5C5C5C]')}>
      <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', dots[p] ?? 'bg-gray-400')} />
      {p}
    </span>
  )
}

// ─── Status Badge ─────────────────────────────────────────────────────────────

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton rounded', className)} />
}

export function TableSkeleton({ rows = 8, cols = 8 }: { rows?: number; cols?: number }) {
  return (
    <tbody>
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i} className="border-b border-[#F0F0F0]">
          {Array.from({ length: cols }).map((_, j) => (
            <td key={j} className="px-3.5 py-[11px]">
              <Skeleton className={cn('h-3', j === 0 ? 'w-20' : j === cols - 1 ? 'w-10' : 'w-24')} />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  )
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

type KpiVariant = 'danger' | 'warning' | 'success' | 'teal' | 'info' | 'default'

const KPI_STYLES: Record<KpiVariant, { border: string; value: string }> = {
  danger:  { border: 'border-l-[3px] border-l-[#E60000]', value: 'text-[#E60000]' },
  warning: { border: 'border-l-[3px] border-l-[#F59E0B]', value: 'text-[#D97706]' },
  success: { border: 'border-l-[3px] border-l-[#16A34A]', value: 'text-[#16A34A]' },
  teal:    { border: 'border-l-[3px] border-l-[#008577]', value: 'text-[#008577]' },
  info:    { border: 'border-l-[3px] border-l-[#0057A8]', value: 'text-[#0057A8]' },
  default: { border: '',                                   value: 'text-[#1A1A1A]' },
}

interface KpiCardProps {
  label: string
  value: string | number
  sub?: string
  delta?: { value: number; label: string }
  variant?: KpiVariant
  icon?: React.ReactNode
  onClick?: () => void
  loading?: boolean
}

export function KpiCard({ label, value, sub, delta, variant = 'default', icon, onClick, loading }: KpiCardProps) {
  const s = KPI_STYLES[variant]
  return (
    <div
      onClick={onClick}
      className={cn(
        'bg-white border border-[#E5E5E5] rounded-lg p-4 relative overflow-hidden transition-all duration-150',
        s.border,
        onClick ? 'cursor-pointer hover:border-[#D0D0D0] hover:shadow-[0_2px_8px_rgba(0,0,0,0.06)]' : '',
      )}
    >
      {icon && (
        <div className="absolute right-3.5 top-3.5 opacity-[0.08] text-[#1A1A1A]">
          {icon}
        </div>
      )}
      <div className="text-[11px] text-[#8C8C8C] font-500 uppercase tracking-[0.5px] mb-2">{label}</div>
      {loading ? (
        <Skeleton className="h-8 w-16 mb-2" />
      ) : (
        <div className={cn('text-[28px] font-700 tracking-tight leading-none', s.value)}>
          {typeof value === 'number' ? value.toLocaleString('en-ZA') : value}
        </div>
      )}
      {(sub || delta) && (
        <div className="flex items-center gap-1.5 mt-2">
          {delta != null && (
            <span className={cn(
              'inline-flex items-center gap-0.5 text-[11px] font-500 px-1.5 py-px rounded',
              delta.value > 0 ? 'text-[#CC0000] bg-[#FFF0F0]' : 'text-[#16A34A] bg-[#EDF7ED]',
            )}>
              {delta.value > 0 ? '↑' : '↓'} {Math.abs(delta.value)} {delta.label}
            </span>
          )}
          {sub && <span className="text-[11px] text-[#8C8C8C]">{sub}</span>}
        </div>
      )}
    </div>
  )
}

// ─── Page Header ──────────────────────────────────────────────────────────────

interface PageHeaderProps {
  breadcrumb: string[]
  title: string
  subtitle?: string
  actions?: React.ReactNode
}

export function PageHeader({ breadcrumb, title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="bg-white border-b border-[#E5E5E5] px-6 py-4 flex items-center gap-4 flex-shrink-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1 text-[11px] text-[#8C8C8C] mb-0.5">
          {breadcrumb.map((crumb, i) => (
            <span key={crumb} className="flex items-center gap-1">
              {i > 0 && <span className="text-[#D0D0D0]">›</span>}
              <span>{crumb}</span>
            </span>
          ))}
        </div>
        <h1 className="text-[18px] font-600 text-[#1A1A1A] tracking-[-0.3px] leading-tight">{title}</h1>
        {subtitle && <p className="text-[12px] text-[#8C8C8C] mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </div>
  )
}

// ─── Btn ──────────────────────────────────────────────────────────────────────

interface BtnProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
  children: React.ReactNode
}

export function Btn({ variant = 'default', size = 'md', loading, children, className, ...props }: BtnProps) {
  const base = 'inline-flex items-center gap-1.5 rounded-md font-500 transition-all cursor-pointer border font-sans disabled:opacity-60 disabled:cursor-not-allowed'
  const sizes = { sm: 'px-2.5 py-1 text-[11px]', md: 'px-3.5 py-[7px] text-[12px]' }
  const variants = {
    default: 'bg-white border-[#D0D0D0] text-[#5C5C5C] hover:bg-[#F5F5F5] hover:text-[#1A1A1A]',
    primary: 'bg-[#E60000] border-[#E60000] text-white hover:bg-[#B30000] hover:border-[#B30000]',
    ghost:   'bg-transparent border-transparent text-[#5C5C5C] hover:bg-[#F5F5F5] hover:text-[#1A1A1A]',
    danger:  'bg-white border-[#F5B8B8] text-[#CC0000] hover:bg-[#FFF0F0]',
  }
  return (
    <button {...props} disabled={props.disabled || loading} className={cn(base, sizes[size], variants[variant], className)}>
      {loading && (
        <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </button>
  )
}

// ─── Empty State ──────────────────────────────────────────────────────────────

export function EmptyState({ title, sub, icon }: { title: string; sub?: string; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      {icon && <div className="text-[#D0D0D0] mb-3">{icon}</div>}
      <p className="text-[13px] font-500 text-[#5C5C5C]">{title}</p>
      {sub && <p className="text-[12px] text-[#8C8C8C] mt-1">{sub}</p>}
    </div>
  )
}

// ─── Tab Group ────────────────────────────────────────────────────────────────

export function TabGroup<T extends string>({
  tabs, value, onChange
}: { tabs: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex bg-[#F5F5F5] border border-[#E5E5E5] rounded-md p-0.5 gap-px">
      {tabs.map(t => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={cn(
            'px-3 py-1.5 rounded text-[11px] font-500 transition-all',
            t.value === value
              ? 'bg-white text-[#1A1A1A] shadow-[0_1px_3px_rgba(0,0,0,0.08)]'
              : 'text-[#5C5C5C] hover:text-[#1A1A1A]'
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

// ─── Tag ──────────────────────────────────────────────────────────────────────

type TagVariant = 'danger' | 'warning' | 'success' | 'info'
const TAG_STYLES: Record<TagVariant, string> = {
  danger:  'bg-[#FFF0F0] text-[#CC0000] border-[#F5B8B8]',
  warning: 'bg-[#FFF8E6] text-[#C47000] border-[#F5D580]',
  success: 'bg-[#EDF7ED] text-[#0A7A0A] border-[#B8DFB8]',
  info:    'bg-[#EEF4FF] text-[#0057A8] border-[#B8CEFF]',
}
export function Tag({ variant, children }: { variant: TagVariant; children: React.ReactNode }) {
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-px rounded text-[11px] font-500 border', TAG_STYLES[variant])}>
      {children}
    </span>
  )
}
