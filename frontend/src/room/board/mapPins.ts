export const PIN = {
  destination: {
    color: '#227e9e', label: 'Destination',
    path: 'M5 21V3m0 1c5-4 9 4 14 0v10c-5 4-9-4-14 0',
  },
  origin: {
    color: '#6f6964', label: 'Starting point',
    path: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM8 12h8m-4-4 4 4-4 4',
  },
  hotel: {
    color: '#8a4f9e', label: 'Stay',
    path: 'M3 20V7m18 13V7M3 12h18M3 17h18M6 12V7h5v5m2 0V7h5v5',
  },
  place: {
    color: '#3a8a3e', label: 'Sight',
    path: 'M3 7h4l2-3h6l2 3h4v13H3ZM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  },
  food: {
    color: '#b85b0d', label: 'Food',
    path: 'M3 3v5a3 3 0 0 0 6 0V3M6 3v18M20 3c-4 2-5 7-5 10h5M20 3v18',
  },
  travel: {
    color: '#28638e', label: 'Travel',
    path: 'm3 10 7 2 7-7c2-2 5 1 3 3l-7 7 2 6-3-1-3-5-5-3Z',
  },
  stop: {
    color: '#42514b', label: 'Other stop',
    path: 'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0ZM14 10a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
  },
}

export type MapPinKind = keyof typeof PIN
