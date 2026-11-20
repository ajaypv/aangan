import { Play, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { MemberForm } from '@/components/family/MemberForm'
import { useApp } from '@/state/AppState'
import { setMe as rememberMe, useMe } from '@/state/me'
import type { Member, ServiceStatus } from '@/types'
import { Avatar, Button, Card, ListCard, ListRow, Pill, Section, Switch, inputClass } from '@/ui/primitives'
import { Sheet } from '@/ui/Sheet'

declare const __APP_VERSION__: string
declare const __APP_BUILD__: string

const SERVICES: { key: 'voice' | 'murf' | 'chat' | 'llm'; name: string; what: string }[] = [
  { key: 'voice', name: 'Voice conversations', what: 'Talk to Aangan in real time, with interruption.' },
  { key: 'murf', name: 'Natural voices', what: "The Murf voice Aangan speaks to you in." },
  { key: 'chat', name: 'Family notifications', what: 'Delivered as Agora Chat messages. Until then they stay in the app.' },
  { key: 'llm', name: 'AI brain', what: 'Understands natural speech. Without it a simpler built-in matcher answers.' },
]

/** Reset needs the word typed, so a stray tap can never empty a family. */
function ResetBody({ onClose }: { onClose: () => void }) {
  const { resetHousehold, snap } = useApp()
  const [text, setText] = useState('')
  const [working, setWorking] = useState(false)
  const ready = text.trim().toLowerCase() === 'reset'
  const people = snap?.members.length ?? 0

  const run = async () => {
    setWorking(true)
    const ok = await resetHousehold()
    setWorking(false)
    if (ok) onClose()
  }

  return (
    <div className="space-y-4">
      <p>
        This deletes <strong>everyone in the household</strong> ({people} {people === 1 ? 'person' : 'people'}) and all of their calendar entries, records, expenses and memories. Aangan goes back to the welcome screen. This cannot be undone.
      </p>
      <label className="block text-sm">
        <span className="mb-1 block font-semibold">Type reset to confirm</span>
        <input className={inputClass} value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} />
      </label>
      <div className="flex justify-end gap-2">
        <Button variant="tertiary" onClick={onClose} disabled={working}>
          Cancel
        </Button>
        <Button variant="danger" disabled={!ready} loading={working} onClick={() => void run()}>
          Reset household
        </Button>
      </div>
    </div>
  )
}

/** Choose who is using this device, or add yourself if you are not listed. */
function SwitchBody({ onClose }: { onClose: () => void }) {
  const { snap, personaId, setMe, notify } = useApp()
  const { markOnboarded } = useMe()
  const [adding, setAdding] = useState(false)
  if (!snap) return null

  if (adding) {
    return (
      <MemberForm
        variant="self"
        submitLabel="Use Aangan as me"
        onCancel={() => setAdding(false)}
        onDone={(m) => {
          rememberMe(m.id)
          markOnboarded()
          notify('success', `Now using Aangan as ${m.name}.`)
          onClose()
        }}
      />
    )
  }

  return (
    <div className="space-y-4">
      <ListCard aria-label="Family members">
        {snap.members.map((m) => (
          <ListRow
            key={m.id}
            className="min-h-[4rem]"
            leading={<Avatar member={m} size={40} ring={m.id === personaId} />}
            title={m.name}
            subtitle={`${m.relation} · ${m.age}`}
            selected={m.id === personaId}
            trailing={m.id === personaId ? <Pill tone="brand">This device</Pill> : undefined}
            onClick={() => {
              if (setMe(m.id)) {
                if (m.id !== personaId) notify('success', `Now using Aangan as ${m.name}.`)
                onClose()
              }
            }}
          />
        ))}
      </ListCard>
      <Button variant="secondary" className="w-full" onClick={() => setAdding(true)}>
        I'm someone new
      </Button>
    </div>
  )
}

function ServiceRow({ name, what, status }: { name: string; what: string; status: ServiceStatus | undefined }) {
  const ok = status?.configured ?? false
  return (
    <ListRow title={name} subtitle={what} trailing={<Pill tone={ok ? 'success' : 'neutral'}>{ok ? 'Connected' : 'Not connected'}</Pill>} />
  )
}

export function SettingsScreen() {
  const { snap, config, member, household, busy, online, trigger, setChaos, reset } = useApp()
  const [sheet, setSheet] = useState<'edit' | 'switch' | 'reset' | null>(null)
  if (!snap) return null
  const close = () => setSheet(null)
  const voice = member ? config?.voices[member.id] : undefined
  const triggers = snap.agents.filter((a) => a.triggers.length > 0)
  const unconnected = SERVICES.filter((s) => config && !config.services[s.key].configured)

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-10 pt-4 lg:px-8">
      <h1 className="t-page mb-4">Settings</h1>

      <Section title="My profile" hint="Who is using Aangan on this device">
        {member && (
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <Avatar member={member} size={56} />
              <div className="min-w-0 flex-1">
                <p className="t-card truncate">{member.name}</p>
                <p className="t-secondary">
                  {member.relation} · {member.age} years old
                </p>
                {voice && <p className="t-caption">{`Aangan's voice with you: ${voice.name} (${voice.gender})`}</p>}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setSheet('edit')}>
                Edit profile
              </Button>
              <Button variant="secondary" onClick={() => setSheet('switch')}>
                Switch profile
              </Button>
            </div>
          </Card>
        )}
      </Section>

      <Section title="Voice and services" hint="What is connected behind Aangan">
        <ListCard aria-label="Services">
          {SERVICES.map((s) => (
            <ServiceRow key={s.key} name={s.name} what={s.what} status={config?.services[s.key]} />
          ))}
        </ListCard>
        {(unconnected.length > 0 || config?.language_mode) && (
          <details className="group mt-3 rounded-md border border-line bg-surface">
            <summary className="flex min-h-11 cursor-pointer list-none items-center px-4 text-sm font-semibold lg:min-h-9">Connection details</summary>
            <div className="space-y-3 border-t border-line px-4 py-3 text-sm">
              {config?.language_mode && (
                <p className="t-secondary">
                  Language: <span className="font-semibold text-ink">{config.language_mode === 'english' ? 'English' : 'Each person’s own language'}</span>
                </p>
              )}
              {unconnected.length === 0 ? (
                <p className="t-secondary">Everything is connected.</p>
              ) : (
                unconnected.map((s) => (
                  <div key={s.key}>
                    <p className="font-semibold">{s.name}</p>
                    <p className="t-secondary">
                      Add to <span className="font-mono">backend/.env</span>:{' '}
                      {(config?.services[s.key].missing ?? []).map((m) => (
                        <code key={m} className="mr-1 inline-block rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs font-semibold text-ink">
                          {m}
                        </code>
                      ))}
                    </p>
                  </div>
                ))
              )}
            </div>
          </details>
        )}
      </Section>

      <Section title="Household" hint={`${snap.members.length} ${snap.members.length === 1 ? 'person' : 'people'}, stored on your Aangan server`}>
        <Card className="space-y-3 p-4">
          {household.demo && <p className="t-secondary">You are looking at the demo family: example people so you can explore. Restore it to its starting state, or reset to begin with your own family.</p>}
          <div className="flex flex-wrap gap-2">
            {household.demo && (
              <Button variant="secondary" icon={<RotateCcw className="size-4" aria-hidden="true" />} loading={busy} onClick={() => void reset()}>
                Restore demo family
              </Button>
            )}
            <Button variant="secondary" className="text-[var(--rw-text-danger)]" icon={<Trash2 className="size-4" aria-hidden="true" />} onClick={() => setSheet('reset')}>
              Reset household
            </Button>
          </div>
        </Card>
      </Section>

      {household.demo && (
        <Section title="Demo scenarios" hint="Make something happen on its own, as it would in real life">
          <div className="space-y-3">
            {triggers.map((a) => (
              <Card key={a.name} className="space-y-2 p-4">
                <p className="t-card">{a.title}</p>
                <div className="flex flex-wrap gap-2">
                  {a.triggers.map((t) => (
                    <Button key={t.name} size="sm" variant="secondary" disabled={busy || !online} icon={<Play className="size-3.5" aria-hidden="true" />} onClick={() => void trigger(a.name, t.name, t.label)}>
                      {t.label}
                    </Button>
                  ))}
                </div>
              </Card>
            ))}
            <Card className="flex items-start justify-between gap-4 p-4">
              <span>
                <span className="block font-semibold">Simulate a supplier failure</span>
                <span className="t-secondary block">The next booking fails once at the supplier, so you can watch Aangan fall back to another option.</span>
              </span>
              <Switch label="Simulate a supplier failure" checked={snap.chaos} disabled={busy} onChange={(on) => void setChaos(on)} />
            </Card>
          </div>
        </Section>
      )}

      <Section title="About">
        <Card className="space-y-1 p-4">
          <p className="font-semibold">Aangan</p>
          <p className="t-secondary num">
            Version {__APP_VERSION__} ({__APP_BUILD__}) · {config?.llm ? config.llm.model : 'built-in matcher'}
          </p>
          <p className="t-secondary">Made for Build with Agora.</p>
        </Card>
      </Section>

      <Sheet open={sheet === 'edit'} title="Edit my profile" onClose={close}>
        {member && <MemberForm variant="edit" initial={member as Member} onCancel={close} onDone={close} />}
      </Sheet>
      <Sheet open={sheet === 'switch'} title="Switch profile" onClose={close}>
        <SwitchBody onClose={close} />
      </Sheet>
      <Sheet open={sheet === 'reset'} title="Reset household" onClose={close}>
        <ResetBody onClose={close} />
      </Sheet>
    </div>
  )
}
