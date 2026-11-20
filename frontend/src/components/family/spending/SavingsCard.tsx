import { Lightbulb, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api'
import { categoryOf, formatINR, rupeeText } from '@/lib/money'
import { useApp } from '@/state/AppState'
import { Button, Card, CardBody, CardHeader, Pill, Skeleton } from '@/ui/primitives'
import { CategoryIcon } from './parts'

interface Idea {
  category: string
  saving: number
  text: string
}

interface Savings {
  enough_data: boolean
  ideas: Idea[]
  potential_savings: number
}

type State = { status: 'idle' } | { status: 'loading' } | { status: 'error' } | { status: 'ready'; data: Savings }

/**
 * Ways to save, from the money agent's suggest_savings tool. It runs when asked, not on every visit, so opening the screen
 * does not add an entry to "What Aangan did".
 */
export function SavingsCard() {
  const { notify } = useApp()
  const [state, setState] = useState<State>({ status: 'idle' })

  const load = async () => {
    setState({ status: 'loading' })
    try {
      const res = await api.tool('money', 'suggest_savings', {})
      if (res.status === 'error') throw new Error(String(res.result.error ?? ''))
      setState({ status: 'ready', data: res.result as unknown as Savings })
    } catch {
      setState({ status: 'error' })
      notify('error', 'Could not look for savings just now. Try again in a moment.')
    }
  }

  return (
    <Card as="section" aria-label="Ways to save">
      <CardHeader
        title="Ways to save"
        subtitle="Specific ideas from your own spending"
        action={
          state.status === 'ready' ? (
            <Button variant="tertiary" size="sm" icon={<RefreshCw className="size-4" aria-hidden="true" />} onClick={load}>
              Refresh
            </Button>
          ) : undefined
        }
      />
      <CardBody className="space-y-3">
        {state.status === 'idle' && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="t-secondary max-w-xs">Aangan checks each category against your budgets and last month, and tells you what could be trimmed.</p>
            <Button icon={<Lightbulb className="size-4" aria-hidden="true" />} onClick={load}>
              Find ways to save
            </Button>
          </div>
        )}
        {state.status === 'loading' && (
          <div role="status" aria-label="Looking for ways to save" className="space-y-3">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        )}
        {state.status === 'error' && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="t-secondary">That did not work.</p>
            <Button variant="secondary" onClick={load}>
              Try again
            </Button>
          </div>
        )}
        {state.status === 'ready' && !state.data.enough_data && (
          <p className="t-secondary">Log a few more expenses this month (at least three) and Aangan can find specific savings.</p>
        )}
        {state.status === 'ready' && state.data.enough_data && state.data.ideas.length === 0 && (
          <p className="t-secondary">Nothing stands out this month. Spending is within budget and in line with last month.</p>
        )}
        {state.status === 'ready' && state.data.enough_data && state.data.ideas.length > 0 && (
          <>
            <p className="text-sm font-semibold">
              You could save about <span className="num">{formatINR(state.data.potential_savings)}</span> a month.
            </p>
            <ul className="space-y-2.5">
              {state.data.ideas.map((idea) => (
                <li key={`${idea.category}-${idea.saving}`} className="flex items-start gap-3 rounded-lg border border-line bg-surface-2 p-3">
                  <CategoryIcon id={idea.category} size={36} />
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold">{categoryOf(idea.category).label}</span>
                      <Pill tone="success">Save about {formatINR(idea.saving)}</Pill>
                    </div>
                    <p className="text-sm leading-snug">{rupeeText(idea.text)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardBody>
    </Card>
  )
}
