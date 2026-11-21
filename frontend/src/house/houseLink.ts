export function houseUrl(base: string): string {
  const url = new URL(base)
  url.search = '?house=cozy-home'
  url.hash = ''
  return url.href
}

export function validateHouseLink(value: string, base: string): 'cozy-home' {
  let url: URL
  try {
    url = new URL(value.trim(), base)
  } catch {
    throw new Error('Enter the Cozy home link shown below.')
  }
  const expected = new URL(houseUrl(base))
  if (url.origin !== expected.origin || url.pathname !== expected.pathname || url.username || url.password ||
      url.searchParams.get('house') !== 'cozy-home' || url.searchParams.has('room')) {
    throw new Error('Use the Cozy home link from this Aangan site. External houses and physical devices are not supported.')
  }
  return 'cozy-home'
}
