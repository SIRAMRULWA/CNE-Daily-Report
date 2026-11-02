'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/lib/auth-context'
import { healthApi } from '@/lib/api'
import { fmtDateTime, cn } from '@/lib/utils'
import { canManageOperations } from '@/lib/permissions'
import { VodacomLogo } from '@/components/ui/VodacomLogo'
import {
  LayoutDashboard, FileText, Activity, Table2, Shield,
  Clock, Settings, Bell, BellRing, Search, Users, Database, Mail,
} from 'lucide-react'

interface NavItem {
  label: string
  href: string
  icon: React.ReactNode
  badge?: number
  operationalAdminOnly?: boolean
}

const NAV_WORKSPACE: NavItem[] = [
  { label: 'Dashboard',   href: '/workspace',         icon: <LayoutDashboard size={15} /> },
  { label: 'Records',     href: '/workspace/records', icon: <Table2 size={15} /> },
  { label: 'SLA Monitor', href: '/workspace/sla',     icon: <Activity size={15} /> },
]

const NAV_REPORTS: NavItem[] = [
  { label: 'Helix Raw Reports', href: '/raw-reports', icon: <Database size={15} /> },
  { label: 'INTSS Daily', href: '/daily-report',       icon: <FileText size={15} /> },
  { label: 'NSD Report',  href: '/daily-report/nsd',   icon: <FileText size={15} /> },
  { label: 'CVDI Report', href: '/daily-report/cvdi',  icon: <FileText size={15} /> },
  { label: 'CDN Report',  href: '/daily-report/cdn',   icon: <FileText size={15} /> },
]

const NAV_ADMIN: NavItem[] = [
  { label: 'Report Emails',   href: '/admin/report-emails', icon: <Mail size={15} />, operationalAdminOnly: true },
  { label: 'Task Reminders', href: '/admin/task-reminders', icon: <BellRing size={15} />, operationalAdminOnly: true },
  { label: 'Divisions',       href: '/divisions',      icon: <Settings size={15} />, operationalAdminOnly: true },
  { label: 'Audit Log',       href: '/admin/audit',    icon: <Shield size={15} />, operationalAdminOnly: true },
  { label: 'Pipeline Status', href: '/admin/pipeline', icon: <Clock size={15} />, operationalAdminOnly: true },
  { label: 'Users',           href: '/admin/users',    icon: <Users size={15} />, operationalAdminOnly: true },
]

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      className={cn(
        'flex items-center gap-2.5 px-2 py-[7px] rounded-md text-[13px] transition-all duration-100 relative select-none',
        active
          ? 'bg-[#FFF0F0] text-[#E60000] font-medium'
          : 'text-[#5C5C5C] hover:bg-[#F5F5F5] hover:text-[#1A1A1A]',
      )}
    >
      {active && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-[70%] bg-[#E60000] rounded-r-sm" />
      )}
      <span className={cn('flex-shrink-0', active ? 'opacity-100' : 'opacity-70')}>
        {item.icon}
      </span>
      <span className="flex-1 truncate">{item.label}</span>
      {item.badge != null && item.badge > 0 && (
        <span className="ml-auto bg-[#E60000] text-white text-[10px] font-600 px-1.5 py-px rounded-full min-w-[18px] text-center">
          {item.badge}
        </span>
      )}
    </Link>
  )
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const [breachedCount, setBreachedCount] = useState<number | null>(null)

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.check,
    refetchInterval: 60_000,
  })

  useEffect(() => {
    if (health?.records?.breached != null) {
      setBreachedCount(health.records.breached)
    }
  }, [health])

  // Build initials from email prefix: "siphamandla.dlamini" → "SD"
  const emailPrefix = user?.email?.split('@')[0] ?? ''
  const initials = emailPrefix.includes('.')
    ? emailPrefix.split('.').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : emailPrefix.slice(0, 2).toUpperCase() || 'SM'

  const isLive = health?.status === 'ok'

  const navWithBadge = NAV_WORKSPACE.map(n =>
    n.href === '/workspace/records' && breachedCount
      ? { ...n, badge: breachedCount }
      : n,
  )

  return (
    <div className="flex flex-col h-screen min-h-0 overflow-hidden bg-[#F5F5F5]">

      {/* ─── TOP BAR ─── */}
      <header className="h-[52px] min-h-[52px] bg-[#E60000] flex items-center px-5 gap-4 z-50 flex-shrink-0">

        {/* Real Vodacom logo — white version on red bg */}
        <div className="flex items-center gap-3">
          {/* Mark only on the left, then wordmark text in white */}
          <VodacomLogo markOnly width={32} className="flex-shrink-0" />
          {/* Override the red fill to white for the topbar using a CSS filter trick */}
          <div className="flex flex-col leading-none">
            <span className="text-white font-800 text-[15px] tracking-tight">Vodacom</span>
            <span className="text-white text-[10px] font-400 tracking-[0.4px] uppercase mt-px">Daily Reports</span>
          </div>
        </div>

        <div className="w-px h-5 bg-white/25" />

        <div className="flex-1" />

        {/* Live indicator */}
        <div className="flex items-center gap-1.5 text-white/80 text-[11px]">
          <span className={cn(
            'w-[7px] h-[7px] rounded-full flex-shrink-0',
            isLive ? 'bg-green-400' : 'bg-white/40',
          )} />
          {isLive
            ? `Live · ${fmtDateTime(health?.pipeline?.last_run_at)?.split('·')[1]?.trim() ?? 'Updated'}`
            : 'Connecting…'}
        </div>

        <div className="w-px h-5 bg-white/25" />

        <button className="flex items-center gap-1.5 bg-white/15 hover:bg-white/25 border border-white/25 text-white px-3 py-1.5 rounded-md text-[12px] transition-colors">
          <Bell size={12} />
          Alerts
        </button>

        <button className="flex items-center gap-1.5 bg-white/15 hover:bg-white/25 border border-white/25 text-white px-3 py-1.5 rounded-md text-[12px] transition-colors">
          <Search size={12} />
          Search
        </button>

        {/* User avatar — click to sign out */}
        <button
          onClick={() => logout()}
          title={`${user?.email ?? ''} — Sign out`}
          className="w-[30px] h-[30px] rounded-full bg-white/20 border-[1.5px] border-white/40 flex items-center justify-center text-white text-[11px] font-600 hover:bg-white/30 transition-colors"
        >
          {initials}
        </button>
      </header>

      {/* ─── BODY ─── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* ─── SIDEBAR ─── */}
        <aside className="w-[220px] min-w-[220px] bg-white border-r border-[#E5E5E5] flex flex-col overflow-y-auto flex-shrink-0">

          {/* Sidebar logo — full wordmark */}
          <div className="px-4 py-4 border-b border-[#F0F0F0] flex items-center">
            <VodacomLogo width={100} />
          </div>

          <div className="px-3 pt-3 pb-1">
            <p className="text-[10px] font-600 text-[#8C8C8C] tracking-[0.8px] uppercase px-2 mb-1.5">
              Operations Console
            </p>
            {navWithBadge.map(item => (
              <NavLink key={item.href} item={item} active={pathname === item.href} />
            ))}
          </div>

          <div className="h-px bg-[#E5E5E5] mx-3 my-1" />

          <div className="px-3 py-2">
            <p className="text-[10px] font-600 text-[#8C8C8C] tracking-[0.8px] uppercase px-2 mb-1.5">
              Reports
            </p>
            {NAV_REPORTS.map(item => (
              <NavLink
                key={item.href}
                item={item}
                active={item.href === '/daily-report'
                  ? pathname === item.href
                  : pathname === item.href || pathname.startsWith(item.href + '/')}
              />
            ))}
          </div>

          <div className="h-px bg-[#E5E5E5] mx-3 my-1" />

          <div className="px-3 py-2">
            <p className="text-[10px] font-600 text-[#8C8C8C] tracking-[0.8px] uppercase px-2 mb-1.5">
              Admin
            </p>
            {NAV_ADMIN
              .filter(item => !item.operationalAdminOnly || canManageOperations(user))
              .map(item => (
                <NavLink
                  key={item.href}
                  item={item}
                  active={pathname === item.href || pathname.startsWith(item.href + '/')}
                />
              ))}
          </div>

          <div className="flex-1" />

          {/* Data freshness footer */}
          <div className="p-3 border-t border-[#E5E5E5]">
            <div className="bg-[#FFF0F0] border border-[#FFE0E0] rounded-md px-3 py-2.5 text-[11px]">
              <div className="font-600 text-[#E60000] mb-0.5">Data as of</div>
              <div className="text-[#5C5C5C]">
                {health?.pipeline?.last_run_at
                  ? fmtDateTime(health.pipeline.last_run_at)
                  : 'No data yet'}
              </div>
            </div>
          </div>
        </aside>

        {/* ─── MAIN CONTENT ─── */}
        <main className="flex-1 overflow-y-auto flex flex-col min-w-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="flex-1 flex flex-col"
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  )
}
