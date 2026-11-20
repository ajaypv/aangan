import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import type { Plan } from '@/types'

/*
 * The map itself (Leaflet with OpenStreetMap tiles). Loaded lazily by MapCard so Leaflet stays out of the main bundle.
 * Pins are plain divs, so there are no marker image files to bundle. Shapes as well as colours tell the kinds apart:
 * destination = big blue circle, origin = grey dot, hotels = purple squares, places = green circles, meals = orange diamonds.
 */
export interface MapPoint {
  key: string
  kind: 'origin' | 'destination' | 'hotel' | 'place' | 'food' | 'stop'
  name: string
  detail: string
  lat: number
  lon: number
}

export const PIN: Record<MapPoint['kind'], { color: string; label: string }> = {
  destination: { color: '#227e9e', label: 'Destination' },
  origin: { color: '#6f6964', label: 'Starting point' },
  hotel: { color: '#8a4f9e', label: 'Stay' },
  place: { color: '#3a8a3e', label: 'Place to visit' },
  food: { color: '#c46a12', label: 'Where to eat' },
  stop: { color: '#312d2a', label: 'Itinerary stop' },
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
  for (const i of plan.itinerary) add({ key: i.id, kind: 'stop', name: i.title, detail: i.place, lat: i.lat, lon: i.lon })
  return out
}

function icon(kind: MapPoint['kind']) {
  const { color } = PIN[kind]
  const size = kind === 'destination' ? 30 : kind === 'origin' || kind === 'stop' ? 14 : 22
  const shape = kind === 'hotel' ? 'border-radius:6px' : kind === 'food' ? 'border-radius:4px;transform:rotate(45deg)' : 'border-radius:9999px'
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div class="room-pin" style="width:${size}px;height:${size}px;background:${color};${shape}"></div>`,
  })
}

export default function MapView({ plan, className }: { plan: Plan; className?: string }) {
  const host = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const fitted = useRef('')
  const pending = useRef<L.LatLngBounds | null>(null)

  useEffect(() => {
    const el = host.current
    if (!el) return
    const touch = window.matchMedia('(pointer: coarse)').matches
    const m = L.map(el, {
      zoomControl: true,
      scrollWheelZoom: false, // the wheel scrolls the page; the +/- buttons and pinch zoom the map
      dragging: !touch, // one finger scrolls the page on a phone; two fingers pan with a pinch
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
      map.current = null
      layer.current = null
    }
  }, [])

  const points = mapPoints(plan)
  const sig = points.map((p) => `${p.key}:${p.lat}:${p.lon}`).join('|')

  useEffect(() => {
    const m = map.current
    const g = layer.current
    if (!m || !g) return
    g.clearLayers()
    const pts = mapPoints(plan)
    for (const p of pts) {
      L.marker([p.lat, p.lon], { icon: icon(p.kind), title: p.name, alt: `${PIN[p.kind].label}: ${p.name}`, keyboard: true, riseOnHover: true })
        .bindPopup(`<strong>${escapeHtml(p.name)}</strong><br>${escapeHtml(p.detail)}`)
        .addTo(g)
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
    if (pts.length > 0 && fitted.current !== sig) {
      fitted.current = sig
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `sig` stands for the points
  }, [sig])

  return <div ref={host} className={className} role="region" aria-label="Trip map" />
}

const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string)
