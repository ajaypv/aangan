import { ArrowLeft, CalendarCheck, HeartPulse, Sparkles, Wallet, X } from 'lucide-react'
import { useState } from 'react'
import { MemberForm } from '@/components/family/MemberForm'
import { Frame, Progress, ScreenHeading } from '@/components/onboarding/Parts'
import { clearSetup, examplePrompts, firstName, loadSetup, saveSetup } from '@/lib/household'
import { useApp } from '@/state/AppState'
import { useMe } from '@/state/me'
import type { Member } from '@/types'
import { Avatar, Button, Card, IconButton, ListCard, ListRow } from '@/ui/primitives'

type Screen = 'welcome' | 'about' | 'family' | 'done' | 'pick' | 'newcomer'

const CAPABILITIES = [
  { icon: CalendarCheck, title: 'Plan and book', text: 'Tables, trips, cabs and a calendar everyone shares.' },
  { icon: HeartPulse, title: 'Look after people', text: 'School updates, medicine reminders and check-ins.' },
  { icon: Wallet, title: 'Track money', text: 'Log spending, set budgets and find savings.' },
  { icon: Sparkles, title: 'Remember what matters', text: 'Allergies, routines and preferences, used in every plan.' },
]

function CapabilityList() {
  return (
    <ul className="space-y-3">
      {CAPABILITIES.map(({ icon: Icon, title, text }) => (
        <li key={title} className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-brand-soft text-brand-text">
            <Icon className="size-5" aria-hidden="true" />
          </span>
          <span>
            <span className="block font-semibold">{title}</span>
            <span className="t-secondary block">{text}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

/**
 * First run and "who is this?". With no one in the household: welcome, then three short steps (about you, your family, all set).
 * With a household but nobody chosen on this device: pick who you are, or add yourself. The shell shows the tabs once someone is chosen.
 */
export function Onboarding() {
  const { snap, loadDemo, setTab, busy } = useApp()
  const { setMe: rememberMe, markOnboarded } = useMe()
  const members = snap?.members ?? []

  const [firstId, setFirstId] = useState<string | null>(() => {
    const saved = loadSetup()
    return saved && members.some((m) => m.id === saved.firstId) ? saved.firstId : null
  })
  const [screen, setScreen] = useState<Screen>(() => {
    if (members.length === 0) return 'welcome'
    const saved = loadSetup()
    if (saved && members.some((m) => m.id === saved.firstId)) return saved.step
    return 'pick'
  })

  // If the household is emptied from elsewhere while the wizard is open, start again from the welcome screen.
  const current: Screen = members.length === 0 && screen !== 'about' ? 'welcome' : screen
  const first = firstId ? members.find((m) => m.id === firstId) : undefined

  const finish = (id: string) => {
    rememberMe(id)
    markOnboarded()
    clearSetup()
    setTab('ask')
  }

  const startDemo = async () => {
    const s = await loadDemo()
    const who = s?.members[0]
    if (who) finish(who.id)
  }

  const created = (m: Member) => {
    setFirstId(m.id)
    saveSetup({ step: 'family', firstId: m.id })
    setScreen('family')
  }

  if (current === 'welcome') {
    return (
      <Frame>
        <ScreenHeading title="Welcome to Aangan">
          One assistant for your whole family. Plans, school, health and spending are looked after, just by asking.
        </ScreenHeading>
        <CapabilityList />
        <div className="flex flex-col gap-2">
          <Button onClick={() => setScreen('about')}>Set up my family</Button>
          <Button variant="tertiary" loading={busy} onClick={() => void startDemo()}>
            Try the demo family
          </Button>
          <p className="t-caption text-center">The demo uses example people so you can look around. You can reset it any time.</p>
        </div>
      </Frame>
    )
  }

  if (current === 'about') {
    return (
      <Frame>
        <Progress step={1} />
        <ScreenHeading title="About you">Aangan uses this to talk with you and to plan around you.</ScreenHeading>
        {first ? (
          <MemberForm variant="edit" initial={first} submitLabel="Continue" onDone={() => setScreen('family')} onCancel={() => setScreen('family')} />
        ) : (
          <MemberForm variant="self" submitLabel="Continue" onDone={created} onCancel={members.length === 0 ? () => setScreen('welcome') : undefined} />
        )}
      </Frame>
    )
  }

  if (current === 'family') {
    return (
      <FamilyStep
        firstId={firstId}
        onBack={() => setScreen('about')}
        onNext={() => {
          if (firstId) saveSetup({ step: 'done', firstId })
          setScreen('done')
        }}
      />
    )
  }

  if (current === 'done') {
    const me = first ?? members[0]
    return (
      <Frame>
        <Progress step={3} />
        <ScreenHeading title={me ? `You're all set, ${firstName(me.name)}` : "You're all set"}>Here is what you can ask Aangan to do.</ScreenHeading>
        <CapabilityList />
        <Card className="p-4">
          <p className="t-card">Try saying</p>
          <ul className="mt-2 space-y-1.5">
            {examplePrompts(members).map((p) => (
              <li key={p} className="t-secondary">
                “{p}”
              </li>
            ))}
          </ul>
        </Card>
        <div className="flex flex-col gap-2">
          <Button disabled={!me} onClick={() => me && finish(me.id)}>
            Start using Aangan
          </Button>
          <Button variant="tertiary" icon={<ArrowLeft className="size-4" aria-hidden="true" />} onClick={() => setScreen('family')}>
            Back
          </Button>
        </div>
      </Frame>
    )
  }

  if (current === 'newcomer') {
    return (
      <Frame>
        <ScreenHeading title="Add yourself">Tell Aangan who you are. This device will remember you.</ScreenHeading>
        <MemberForm variant="self" submitLabel="Start using Aangan" onDone={(m) => finish(m.id)} onCancel={() => setScreen('pick')} />
      </Frame>
    )
  }

  // pick
  return (
    <Frame>
      <ScreenHeading title="Who's using Aangan?">This device will remember your choice. You can switch any time in Settings.</ScreenHeading>
      <ListCard aria-label="Family members">
        {members.map((m) => (
          <ListRow
            key={m.id}
            className="min-h-[4.25rem]"
            leading={<Avatar member={m} size={44} />}
            title={m.name}
            subtitle={`${m.relation} · ${m.age}`}
            onClick={() => finish(m.id)}
          />
        ))}
      </ListCard>
      <Button variant="secondary" onClick={() => setScreen('newcomer')}>
        I'm someone new
      </Button>
    </Frame>
  )
}

/** Step 2: add the other people one by one. The profile created in step 1 is not listed here. */
function FamilyStep({ firstId, onBack, onNext }: { firstId: string | null; onBack: () => void; onNext: () => void }) {
  const { snap, runTool, notify } = useApp()
  const [formKey, setFormKey] = useState(0)
  const [removing, setRemoving] = useState<string | null>(null)
  const others = (snap?.members ?? []).filter((m) => m.id !== firstId)

  const remove = async (m: Member) => {
    setRemoving(m.id)
    const outcome = await runTool('household', 'remove_member', { member_id: m.id, confirm: true })
    setRemoving(null)
    if (!outcome.ok) notify('error', outcome.error ?? `${m.name} could not be removed.`)
  }

  return (
    <Frame>
      <Progress step={2} />
      <ScreenHeading title="Who else is in your family?">Add the people Aangan should look after. You can add more later in Family.</ScreenHeading>

      {others.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="People added so far">
          {others.map((m) => (
            <li key={m.id} className="inline-flex items-center gap-2 rounded-full border border-line bg-surface py-1 pl-1.5 pr-1 shadow-xs">
              <Avatar member={m} size={26} />
              <span className="text-sm font-semibold">
                {m.name} <span className="t-secondary font-normal">· {m.relation}</span>
              </span>
              <IconButton label={`Remove ${m.name}`} tooltip={false} className="-my-1 -mr-0.5" disabled={removing === m.id} onClick={() => void remove(m)}>
                <X className="size-4" aria-hidden="true" />
              </IconButton>
            </li>
          ))}
        </ul>
      )}

      <Card className="p-4">
        <MemberForm
          key={formKey}
          variant="other"
          submitLabel="Add person"
          submitVariant="secondary"
          autoFocus={others.length > 0}
          onDone={() => setFormKey((k) => k + 1)}
        />
      </Card>

      <div className="flex flex-col gap-2">
        <Button onClick={onNext}>{others.length > 0 ? 'Continue' : "I'll add them later"}</Button>
        <Button variant="tertiary" icon={<ArrowLeft className="size-4" aria-hidden="true" />} onClick={onBack}>
          Back
        </Button>
      </div>
    </Frame>
  )
}
