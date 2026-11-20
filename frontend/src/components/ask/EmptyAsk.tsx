import { Mic } from 'lucide-react'
import type { Member, Snapshot } from '@/types'
import { Button } from '@/ui/primitives'
import { capabilityCards } from './capabilities'

/** What an empty conversation shows: a greeting, one big way to talk, and a few starter ideas that fit this household. */
export function EmptyAsk({ snap, me, busy, onSend, onVoice }: { snap: Snapshot; me: Member; busy: boolean; onSend: (text: string) => void; onVoice: () => void }) {
  const first = me.name.trim().split(/\s+/)[0]
  const cards = capabilityCards(snap, me)
  return (
    <div className="mx-auto w-full max-w-2xl py-2 lg:py-6">
      <div className="text-center">
        <h2 className="t-page">Hi {first}, what can I help with?</h2>
        <p className="t-secondary mt-1.5">Talk or type. Aangan plans, books, reminds and keeps track for the whole family.</p>
        <Button className="mt-5 min-w-52" icon={<Mic className="size-5" aria-hidden="true" />} onClick={onVoice}>
          Talk to Aangan
        </Button>
        <p className="t-caption mt-2">or type below, or tap an idea</p>
      </div>
      <ul className="mt-6 grid gap-2.5 sm:grid-cols-2" aria-label="Things you could ask">
        {cards.map(({ id, title, phrase, icon: Icon }) => (
          <li key={id}>
            <button
              type="button"
              disabled={busy}
              onClick={() => onSend(phrase)}
              className="flex min-h-[4.5rem] w-full items-start gap-3 rounded-xl border border-line bg-surface p-3.5 text-left shadow-xs transition-colors hover:border-edge hover:bg-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-text" aria-hidden="true">
                <Icon className="size-[18px]" />
              </span>
              <span className="min-w-0">
                <span className="block font-semibold">{title}</span>
                <span className="t-secondary block">“{phrase}”</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
