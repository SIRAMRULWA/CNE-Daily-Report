'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ReportPeriod = 'day' | 'week'

interface ReportDateContextType {
  reportDate: string
  period: ReportPeriod
  setReportDate: (date: string) => void
  setPeriod: (period: ReportPeriod) => void
  today: string
  isToday: boolean
}

const PERIOD_STORAGE_KEY = 'vodacom-report-period'

function todayIso() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Africa/Johannesburg',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

function validPeriod(value: string | null): ReportPeriod {
  return value === 'week' ? 'week' : 'day'
}

const ReportDateContext = createContext<ReportDateContextType | null>(null)

export function ReportDateProvider({ children }: { children: ReactNode }) {
  const today = todayIso()
  const [reportDate, setReportDateState] = useState(today)
  const [period, setPeriodState] = useState<ReportPeriod>('day')

  useEffect(() => {
    const storedPeriod = window.localStorage.getItem(PERIOD_STORAGE_KEY)
    setPeriodState(validPeriod(storedPeriod))
  }, [])

  const setReportDate = useCallback((date: string) => {
    const nextDate = date || todayIso()
    setReportDateState(nextDate)
  }, [])

  const setPeriod = useCallback((nextPeriod: ReportPeriod) => {
    setPeriodState(nextPeriod)
    window.localStorage.setItem(PERIOD_STORAGE_KEY, nextPeriod)
  }, [])

  const value = useMemo(
    () => ({
      reportDate,
      period,
      setReportDate,
      setPeriod,
      today,
      isToday: reportDate === today,
    }),
    [period, reportDate, setPeriod, setReportDate, today],
  )

  return (
    <ReportDateContext.Provider value={value}>
      {children}
    </ReportDateContext.Provider>
  )
}

export function useReportDate() {
  const ctx = useContext(ReportDateContext)
  if (!ctx) throw new Error('useReportDate must be used inside ReportDateProvider')
  return ctx
}
