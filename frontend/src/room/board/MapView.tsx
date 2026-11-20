import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import type { Plan } from '@/types'
import { PIN, type MapPinKind } from './mapPins'
import { itineraryRoutes } from './mapRoutes'

/*
 * The map itself (Leaflet with OpenStreetMap tiles). Loaded lazily by MapCard so Leaflet stays out of the main bundle.
 * Pins use local SVG pictograms shared with the legend, so categories do not rely on colour alone.
 */
export interface MapPoint {
  key: string
  kind: MapPinKind
  name: string
  detail: string
  lat: number
  lon: number
}

/** Every point worth a pin, without two pins on the same spot (a meal on the itinerary is the same pin as the restaurant). */
export function mapPoints(plan: Plan): MapPoint[] {
  const out: MapPoint[] = []
  const seen = new Set<string>()
  const at = (lat: number, lon: number) => `${lat.toFixed(4)},${lon.toFixed(4)}`
  const add = (p: MapPoint) => {
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lon)) return
    const k = at(p.lat, p.lon)
    if (seen.has(k) && p.kind !== 'origin' && p.kind !== 'destination') return
    seen.add(k)
    out.push(p)
  }
  if (plan.origin) add({ key: 'origin', kind: 'origin', name: plan.origin.name, detail: 'Starting point', lat: plan.origin.lat, lon: plan.origin.lon })
  if (plan.destination) add({ key: 'dest', kind: 'destination', name: plan.destination.name, detail: 'Destination', lat: plan.destination.lat, lon: plan.destination.lon })
  for (const h of plan.hotels.filter((x) => x.status !== 'rejected')) add({ key: h.id, kind: 'hotel', name: h.name, detail: `Stay, ${h.area}`, lat: h.lat, lon: h.lon })
  for (const x of plan.places.filter((p) => p.status !== 'rejected')) add({ key: x.id, kind: 'place', name: x.name, detail: x.area, lat: x.lat, lon: x.lon })
  for (const r of plan.restaurants.filter((x) => x.status !== 'rejected')) add({ key: r.id, kind: 'food', name: r.name, detail: `${r.cuisine}, ${r.area}`, lat: r.lat, lon: r.lon })
  for (const i of plan.itinerary) {
    const kind = i.kind === 'travel' ? 'travel' : i.kind === 'stay' ? 'hotel' : i.kind === 'food' ? 'food' : i.kind === 'place' ? 'place' : 'stop'
    add({ key: i.id, kind, name: i.title, detail: i.place, lat: i.lat, lon: i.lon })
  }
  return out
}

function icon(kind: MapPoint['kind']) {
  const { color, path } = PIN[kind]
  return L.divIcon({
    className: 'room-map-marker',
    iconSize: [44, 44],
    iconAnchor: [22, 22],
    popupAnchor: [0, -18],
    html: `<div class="room-pin room-pin--${kind}" style="background:${color}" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg></div>`,
  })
}

export default function MapView({ plan, className, day = null, expanded = false }: { plan: Plan; className?: string; day?: number | null; expanded?: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const routes = useRef(new Map<number, { signature: string; line: L.Polyline }>())
  const rendered = useRef(false)
  const fitted = useRef('')
  const pending = useRef<L.LatLngBounds | null>(null)

  useEffect(() => {
    const el = host.current
    if (!el) return
    const touch = window.matchMedia('(pointer: coarse)').matches
    const m = L.map(el, {
      zoomControl: true,
      scrollWheelZoom: expanded,
      dragging: expanded || !touch, // The embedded map lets one finger scroll the page; the expanded map lets it pan.
      attributionControl: true,
    }).setView([15.3, 74.1], 8)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
    }).addTo(m)
    layer.current = L.layerGroup().addTo(m)
    map.current = m

    // The board can be hidden (phone tabs) or resized: tell Leaflet, and finish a fit that was waiting for a real size.
    const ro = new ResizeObserver(() => {
      if (el.clientWidth === 0 || el.clientHeight === 0) return
      m.invalidateSize()
      if (pending.current) {
        m.fitBounds(pending.current, { padding: [28, 28], maxZoom: 12 })
        pending.current = null
      }
    })
    ro.observe(el)
    return () => {
      ro.disconnect()
      m.remove()
      routes.current.clear()
      rendered.current = false
      fitted.current = ''
      pending.current = null
      map.current = null
      layer.current = null
    }
  }, [expanded])

  const points = mapPoints(plan)
  const sig = JSON.stringify([points, itineraryRoutes(plan.itinerary), day])

  useEffect(() => {
    const m = map.current
    const g = layer.current
    if (!m || !g) return
    g.clearLayers()
    const pts = mapPoints(plan)
    for (const p of pts) {
      const marker = L.marker([p.lat, p.lon], { icon: icon(p.kind), title: p.name, keyboard: true, riseOnHover: true })
        .bindTooltip(escapeHtml(p.name), { direction: 'top', offset: [0, -18] })
        .bindPopup(`<strong>${escapeHtml(p.name)}</strong><br>${escapeHtml(p.detail)}`)
        .addTo(g)
      marker.getElement()?.setAttribute('aria-label', `${PIN[p.kind].label}: ${p.name}`)
    }
    if (plan.origin && plan.destination) {
      L.polyline(
        [
          [plan.origin.lat, plan.origin.lon],
          [plan.destination.lat, plan.destination.lon],
        ],
        { color: PIN.destination.color, weight: 3, opacity: 0.8, dashArray: '8 8' },
      ).addTo(g)
    }
    const nextRoutes = itineraryRoutes(plan.itinerary).filter((route) => day === null || route.day === day)
    for (const [day, route] of routes.current) {
      if (!nextRoutes.some((next) => next.day === day)) {
        route.line.remove()
        routes.current.delete(day)
      }
    }
    for (const route of nextRoutes) {
      const signature = JSON.stringify(route.points)
      const previous = routes.current.get(route.day)
      if (previous?.signature === signature) continue
      previous?.line.remove()
      const line = L.polyline(route.points, {
        color: '#3a8a6e',
        weight: 3,
        opacity: 0.85,
        className: `room-itinerary-route${rendered.current ? ' room-route-draw' : ''}`,
      }).bindTooltip(`Day ${route.day}: planned stop order (not driving directions)`).addTo(m)
      line.getElement()?.setAttribute('pathLength', '1')
      routes.current.set(route.day, { signature, line })
    }
    rendered.current = true
    const boundsKey = pts.map((p) => `${p.key}:${p.lat}:${p.lon}`).join('|')
    if (pts.length > 0 && fitted.current !== boundsKey) {
      fitted.current = boundsKey
      // Once there are places on the ground, frame those (the dashed route still shows toward the starting point); before that, frame the whole route.
      const local = pts.filter((p) => p.kind !== 'origin')
      const framed = local.length > 1 ? local : pts
      const bounds = L.latLngBounds(framed.map((p) => [p.lat, p.lon] as [number, number]))
      const el = host.current
      if (el && el.clientWidth > 0 && el.clientHeight > 0) {
        m.invalidateSize()
        m.fitBounds(bounds, { padding: [28, 28], maxZoom: 12 })
      } else pending.current = bounds
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `sig` stands for pin content and ordered routes.
  }, [sig, expanded])

  return <div ref={host} className={className} role="region" aria-label="Trip map" />
}

const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string)
