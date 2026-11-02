import { NextResponse } from 'next/server'

export const dynamic = 'force-static'

export function GET() {
  return NextResponse.json({
    ok: true,
    service: 'vodacom-itil-reports-fe',
    timestamp: new Date().toISOString(),
  })
}
