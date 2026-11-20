import assert from 'node:assert/strict'
import { test } from 'node:test'
import { itineraryRoutes } from '../src/room/board/mapRoutes.ts'

test('connects each day in time order without mutating the itinerary or joining separate days', () => {
  const items = [
    { day: 2, time: '12:00', lat: 16, lon: 74 },
    { day: 1, time: '14:00', lat: 15.2, lon: 73.8 },
    { day: 1, time: '09:00', lat: 15.1, lon: 73.7 },
    { day: 2, time: '08:00', lat: 16.1, lon: 74.1 },
  ]
  const before = structuredClone(items)
  assert.deepEqual(itineraryRoutes(items), [
    { day: 1, points: [[15.1, 73.7], [15.2, 73.8]] },
    { day: 2, points: [[16.1, 74.1], [16, 74]] },
  ])
  assert.deepEqual(items, before)
})

test('omits invalid coordinates and zero-length routes but retains return visits', () => {
  assert.deepEqual(itineraryRoutes([
    { day: 1, time: '08:00', lat: 15, lon: 73 },
    { day: 1, time: '09:00', lat: 15, lon: 73 },
    { day: 1, time: '10:00', lat: NaN, lon: 73 },
    { day: 1, time: '11:00', lat: 95, lon: 73 },
    { day: 1, time: '12:00', lat: 15, lon: Infinity },
    { day: 1, time: '13:00', lat: 15, lon: 181 },
    { day: 1, time: '14:00', lat: 16, lon: 74 },
    { day: 1, time: '15:00', lat: 15, lon: 73 },
    { day: 2, time: '08:00', lat: 15, lon: 73 },
    { day: 2, time: '09:00', lat: 15, lon: 73 },
  ]), [{ day: 1, points: [[15, 73], [16, 74], [15, 73]] }])
  assert.deepEqual(itineraryRoutes([]), [])
})
