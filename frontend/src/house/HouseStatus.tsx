import { ExternalLink, House, Lightbulb, Tv } from 'lucide-react'
import { useApp } from '@/state/AppState'
import { HOUSE_ROOMS } from './types'
import { houseUrl } from './houseLink'

export function HouseStatus() {
  const { snap } = useApp()
  const house = snap?.domains.smart_home
  if (!house?.linked) return null
  return (
    <div className="mx-4 mt-3 rounded-lg border border-line bg-surface px-3 py-2">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="inline-flex items-center gap-2 font-semibold"><House className="size-4 text-brand-text" aria-hidden="true" />House linked <span className="font-normal text-ink-2">Virtual</span></span>
        <a className="inline-flex min-h-9 items-center gap-1 font-semibold text-brand-text underline underline-offset-4" href={houseUrl(location.href)} target="_blank" rel="noopener noreferrer">
          View house <ExternalLink className="size-3.5" aria-hidden="true" />
        </a>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-2" aria-label="House lights">
        {HOUSE_ROOMS.map((key) => <span key={key} className="inline-flex items-center gap-1">
          <Lightbulb className={`size-3 ${house.lights[key].on ? 'text-brand-text' : ''}`} aria-hidden="true" />
          {house.lights[key].name}: {house.lights[key].on ? `${house.lights[key].brightness}%` : 'off'}
        </span>)}
        <span className="inline-flex items-center gap-1"><Tv className="size-3" aria-hidden="true" />TV: {house.tv ? house.tv.on ? 'on' : 'off' : 'backend update needed'}</span>
      </div>
    </div>
  )
}
