import { useEffect, useState } from 'react'

export interface ImpactKind {
  key: string
  label: string
  count: number
  minutes_saved: number
}

export interface Money {
  currency: string
  month_total: number
  budget_total: number | null
  budget_left: number | null
  potential_savings: number
  top_tip: string
}

/** What Aangan has done for the family. Mirrors GET /api/impact; every field tolerates being absent. */
export interface Impact {
  actions: number
  minutes_saved: number
  by_kind: ImpactKind[]
  alerts: number
  notifications: number
  money: Money | null
  assumptions: string[]
}

export type ImpactResult = { status: 'loading' } | { status: 'unavailable' } | { status: 'ready'; impact: Impact }

const num = (v: unknown, fallback = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : fallback)
const nullableNum = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)

function parse(raw: unknown): Impact {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const m = r.money && typeof r.money === 'object' ? (r.money as Record<string, unknown>) : null
  return {
    actions: num(r.actions),
    minutes_saved: num(r.minutes_saved),
    by_kind: Array.isArray(r.by_kind) ? (r.by_kind as ImpactKind[]) : [],
    alerts: num(r.alerts),
    notifications: num(r.notifications),
    assumptions: Array.isArray(r.assumptions) ? r.assumptions.filter((a): a is string => typeof a === 'string') : [],
    money: m
      ? {
          currency: typeof m.currency === 'string' ? m.currency : 'INR',
          month_total: num(m.month_total),
          budget_total: nullableNum(m.budget_total),
          budget_left: nullableNum(m.budget_left),
          potential_savings: num(m.potential_savings),
          top_tip: typeof m.top_tip === 'string' ? m.top_tip : '',
        }
      : null,
  }
}

/** Loads /api/impact and reloads when `refreshKey` changes (for example when Aangan has done something new). A 404 or an error is just "unavailable". */
export function useImpact(refreshKey: string | number): ImpactResult {
  const [result, setResult] = useState<ImpactResult>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetch('/api/impact')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((json) => !cancelled && setResult({ status: 'ready', impact: parse(json) }))
      .catch(() => !cancelled && setResult((cur) => (cur.status === 'ready' ? cur : { status: 'unavailable' })))
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  return result
}
