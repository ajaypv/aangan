import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { Resvg } from '@resvg/resvg-js'

const publicDir = new URL('../public/', import.meta.url)
const mark = await readFile(new URL('brand-mark.svg', publicDir), 'utf8')

// The mark is drawn on a 128 grid; `scale` shrinks it toward the centre so maskable icons keep it inside the safe zone.
const drawing = (scale) => {
  const inner = mark.replace('<svg ', '<svg x="0" y="0" width="512" height="512" ')
  const offset = (512 - 512 * scale) / 2
  return `<g transform="translate(${offset} ${offset}) scale(${scale})">${inner}</g>`
}

// Redwood brand teal (--rw-brand-120, rgb 0 104 140) behind a white mark.
const icon = (rounded, scale) => `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" color="#ffffff">
  <rect width="512" height="512" rx="${rounded ? 112 : 0}" fill="#00688c"/>
  ${drawing(scale)}
</svg>
`

await writeFile(new URL('favicon.svg', publicDir), icon(true, 1))
for (const [name, size, rounded, scale] of [
  ['icon-192.png', 192, true, 1],
  ['icon-512.png', 512, true, 1],
  ['icon-maskable-512.png', 512, false, 0.72],
  ['apple-touch-icon.png', 180, false, 0.86],
]) {
  const image = new Resvg(icon(rounded, scale), { fitTo: { mode: 'width', value: size } }).render()
  await writeFile(new URL(`icons/${name}`, publicDir), image.asPng())
  console.log(`Generated ${fileURLToPath(new URL(`icons/${name}`, publicDir))} (${size} x ${size})`)
}
