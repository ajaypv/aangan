import { CalendarDays, MessageSquareText, Users, Wallet, Wrench } from 'lucide-react'
import { ScheduleView } from '@/components/family/Schedule'
import { SpendingView } from '@/components/family/Spending'
import { cn } from '@/lib/utils'
import { ActivityScreen } from '@/screens/Activity'
import { Family } from '@/screens/Family'
import { Ask } from '@/screens/Ask'
import { useApp } from '@/state/AppState'
import { ProgressStrip } from './ProgressStrip'
import { SegmentedControl } from './primitives'

/**
 * Ask is one place with two views: the conversation, and "What Aangan did" (the actions it took). The progress strip (Before, During,
 * Action, After) floats here only, and only while a request runs.
 */
export function AskTab() {
  const { view, setTab } = useApp()
  const current = view === 'did' ? 'did' : 'chat'
  return (
    <div className="relative flex h-full flex-col">
      <div className="px-4 pt-3 lg:px-8">
        <SegmentedControl
          label="Ask views"
          value={current}
          onChange={(v) => setTab('ask', v === 'did' ? 'did' : null)}
          options={[
            { value: 'chat', label: 'Conversation', icon: <MessageSquareText className="size-4" aria-hidden="true" /> },
            { value: 'did', label: 'What Aangan did', icon: <Wrench className="size-4" aria-hidden="true" /> },
          ]}
        />
      </div>
      <ProgressStrip className="top-16" />
      <div className={cn('min-h-0 flex-1', current === 'did' ? 'overflow-y-auto' : 'overflow-hidden')}>{current === 'did' ? <ActivityScreen /> : <Ask />}</div>
    </div>
  )
}

/** Family is one place with three views: the people (and what Aangan remembers about them), the shared schedule, and spending. */
export function FamilyTab() {
  const { view, setTab } = useApp()
  const current = view === 'schedule' ? 'schedule' : view === 'spending' ? 'spending' : 'people'
  return (
    <div>
      <div className="px-4 pt-3 lg:px-8">
        <SegmentedControl
          label="Family views"
          value={current}
          onChange={(v) => setTab('family', v === 'people' ? null : v)}
          options={[
            { value: 'people', label: 'People', icon: <Users className="size-4" aria-hidden="true" /> },
            { value: 'schedule', label: 'Schedule', icon: <CalendarDays className="size-4" aria-hidden="true" /> },
            { value: 'spending', label: 'Spending', icon: <Wallet className="size-4" aria-hidden="true" /> },
          ]}
        />
      </div>
      {current === 'schedule' ? <ScheduleView /> : current === 'spending' ? <SpendingView /> : <Family />}
    </div>
  )
}
