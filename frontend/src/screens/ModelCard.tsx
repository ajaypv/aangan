import { Check, FlaskConical, Search, Undo2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '@/api'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/AppState'
import type { LlmModel, LlmTestResult, ModelKind } from '@/types'
import { Button, Card, Pill, SegmentedControl, Switch, inputClass } from '@/ui/primitives'

const SEARCH_DELAY_MS = 250

/** 128000 becomes "128K", 1000000 becomes "1M". */
function contextLabel(n: number | null): string {
  if (!n) return ''
  return n >= 1_000_000 ? `${Math.round(n / 100_000) / 10}M` : `${Math.round(n / 1000)}K`
}

const dollars = (n: number) => (n < 1 ? n.toFixed(2) : n.toFixed(n < 10 ? 2 : 0))

function priceLabel(m: LlmModel): string {
  if (m.input_per_million === null || m.output_per_million === null) return 'Price not listed'
  if (m.input_per_million === 0 && m.output_per_million === 0) return 'Free'
  return `$${dollars(m.input_per_million)} in · $${dollars(m.output_per_million)} out per 1M tokens`
}

function TestLine({ result, testing }: { result: LlmTestResult | undefined; testing: boolean }) {
  if (testing) return <p className="t-caption">Testing the model…</p>
  if (!result) return null
  if (!result.ok) return <p role="status" className="t-caption font-semibold text-[var(--rw-text-danger)]">{result.error}</p>
  return (
    <p role="status" className={cn('t-caption font-semibold', result.tool_calling ? 'text-[var(--rw-text-success)]' : 'text-[var(--rw-text-warning)]')}>
      {result.ms >= 1000 ? `${(result.ms / 1000).toFixed(1)} s` : `${result.ms} ms`}. {result.note}
    </p>
  )
}

/**
 * Pick the AI model Aangan thinks with. Search the AI Gateway's models (by name, maker or what they are good at), see what they
 * cost and whether they can use tools (Aangan's agents act through tools), try one, and choose it. One model for English and
 * general use, and optionally another for Hindi, Telugu and Kannada.
 */
export function ModelCard() {
  const { config, reload, notify } = useApp()
  const llm = config?.llm
  const [kind, setKind] = useState<ModelKind>('main')
  const [query, setQuery] = useState('')
  const [toolsOnly, setToolsOnly] = useState(true)
  const [models, setModels] = useState<LlmModel[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [problem, setProblem] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  const [tests, setTests] = useState<Record<string, LlmTestResult>>({})
  const [testing, setTesting] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const latest = useRef(0)

  // Search as you type, after a short pause. A slow answer to an old search never replaces a newer one.
  useEffect(() => {
    if (!llm?.choosable) return
    const mine = ++latest.current
    setLoading(true)
    setShowAll(false)
    const timer = window.setTimeout(async () => {
      try {
        const res = await api.llm.models(query, toolsOnly)
        if (mine !== latest.current) return
        setModels(res.models)
        setTotal(res.total)
        setProblem(null)
      } catch (e) {
        if (mine !== latest.current) return
        setModels([])
        setProblem(e instanceof ApiError ? e.message : 'Could not load the models.')
      } finally {
        if (mine === latest.current) setLoading(false)
      }
    }, query ? SEARCH_DELAY_MS : 0)
    return () => window.clearTimeout(timer)
  }, [query, toolsOnly, llm?.choosable])

  if (!llm?.choosable) return null

  const PREVIEW = 6
  const shown = showAll ? models : models.slice(0, PREVIEW)
  const current = kind === 'main' ? llm.model : (llm.indic_model ?? llm.model)
  const chosen = llm.overrides?.[kind]
  const fallback = llm.defaults?.[kind]

  const choose = async (model: string | null) => {
    setSaving(model ?? 'default')
    try {
      await api.llm.choose(model, kind)
      reload()
      notify('success', model ? `Aangan will think with ${model} from the next message.` : 'Back to the default model.')
      if (model) void runTest(model)
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not change the model. Try again.')
    } finally {
      setSaving(null)
    }
  }

  const runTest = async (model: string) => {
    setTesting(model)
    try {
      const result = await api.llm.test(model)
      setTests((t) => ({ ...t, [model]: result }))
    } catch (e) {
      setTests((t) => ({ ...t, [model]: { ok: false, model, ms: 0, error: e instanceof ApiError ? e.message : 'The test did not go through.' } }))
    } finally {
      setTesting(null)
    }
  }

  return (
    <Card className="mt-3 space-y-3 p-4">
      <div>
        <p className="t-card">AI model</p>
        <p className="t-secondary">The model Aangan thinks with. Search the gateway&rsquo;s models, try one, and switch. It applies from the next message.</p>
      </div>

      <SegmentedControl<ModelKind>
        label="Which conversations"
        value={kind}
        onChange={(k) => setKind(k)}
        options={[
          { value: 'main', label: 'English and general' },
          { value: 'indic', label: 'हिन्दी · తెలుగు · ಕನ್ನಡ' },
        ]}
      />

      <div className="space-y-1 rounded-md bg-surface-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="min-w-0 flex-1 break-all font-mono text-sm font-semibold">{current}</p>
          <Pill tone={chosen ? 'brand' : 'neutral'}>{chosen ? 'Your choice' : 'Default'}</Pill>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" icon={<FlaskConical className="size-4" aria-hidden="true" />} loading={testing === current} onClick={() => void runTest(current)}>
            Test
          </Button>
          {chosen && (
            <Button size="sm" variant="tertiary" icon={<Undo2 className="size-4" aria-hidden="true" />} loading={saving === 'default'} onClick={() => void choose(null)}>
              Use the default{fallback ? ` (${fallback.split('/').pop()})` : ''}
            </Button>
          )}
        </div>
        <TestLine result={tests[current]} testing={testing === current} />
      </div>

      <div className="space-y-2">
        <label className="relative block">
          <span className="sr-only">Search models</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-2" aria-hidden="true" />
          <input
            type="search"
            className={cn(inputClass, 'pl-9')}
            placeholder="Search models: gemini, mini, fast, hindi…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold">Only models that can use tools</p>
            <p className="t-caption">Aangan&rsquo;s agents act through tools. A model without them can chat but not book or plan.</p>
          </div>
          <Switch label="Only models that can use tools" checked={toolsOnly} onChange={setToolsOnly} />
        </div>
      </div>

      <p className="t-caption" role="status" aria-live="polite">
        {problem ? problem : loading ? 'Searching…' : `${models.length} of ${total} models${query ? ` match “${query}”` : ''}${models.length === 30 ? '. Type to narrow it down.' : ''}`}
      </p>

      {problem ? null : (
        <ul className="divide-y divide-line rounded-md border border-line" aria-label="Models">
          {shown.map((m) => {
            const on = m.id === current
            return (
              <li key={m.id} className={cn('space-y-1.5 px-3 py-3', on && 'bg-brand-soft')}>
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold leading-snug">{m.name}</p>
                    <p className="t-caption break-all font-mono">{m.id}</p>
                  </div>
                  <Button
                    size="sm"
                    variant={on ? 'secondary' : 'primary'}
                    disabled={on}
                    loading={saving === m.id}
                    icon={on ? <Check className="size-4" aria-hidden="true" /> : undefined}
                    onClick={() => void choose(m.id)}
                    aria-label={on ? `${m.name} is in use` : `Use ${m.name}`}
                  >
                    {on ? 'In use' : 'Use'}
                  </Button>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {m.tools ? <Pill tone="success">Tools</Pill> : <Pill>No tools</Pill>}
                  {m.fast && <Pill tone="info">Fast</Pill>}
                  {m.reasoning && <Pill>Reasoning</Pill>}
                  {m.context_window ? <Pill>{contextLabel(m.context_window)} context</Pill> : null}
                </div>
                <p className="t-caption num">{priceLabel(m)}</p>
                {m.description && <p className="t-secondary line-clamp-2">{m.description}</p>}
                <TestLine result={tests[m.id]} testing={testing === m.id} />
              </li>
            )
          })}
        </ul>
      )}
      {!problem && models.length > PREVIEW && (
        <Button variant="secondary" className="w-full" onClick={() => setShowAll((open) => !open)} aria-expanded={showAll}>
          {showAll ? 'Show fewer' : `Show all ${models.length} results`}
        </Button>
      )}
    </Card>
  )
}
