import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const base = process.env.BASE_PATH ?? '/'
const version: string = JSON.parse(readFileSync('./package.json', 'utf8')).version
const build = process.env.GITHUB_SHA?.slice(0, 7) ?? 'local'
const backend = process.env.AANGAN_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  base,
  define: {
    __APP_VERSION__: JSON.stringify(version),
    __APP_BUILD__: JSON.stringify(build),
  },
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: 5190,
    proxy: { '/api': backend, '/v1': backend },
  },
  preview: {
    port: 5191,
    proxy: { '/api': backend, '/v1': backend },
  },
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'react', test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
            { name: 'agora', test: /node_modules[\\/](agora-rtc-sdk-ng|agora-rtm|agora-agent-client-toolkit)[\\/]/ },
          ],
        },
      },
    },
  },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'prompt',
      injectRegister: false,
      manifest: {
        name: 'Aangan',
        short_name: 'Aangan',
        description: 'A family voice assistant that remembers everyone and gets things done.',
        start_url: base,
        scope: base,
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#fbf9f8',
        theme_color: '#fbf9f8',
        categories: ['lifestyle', 'productivity'],
        shortcuts: [
          { name: 'Ask Aangan', short_name: 'Ask', url: `${base}?tab=ask`, icons: [{ src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' }] },
          { name: 'Family schedule', short_name: 'Schedule', url: `${base}?tab=family&view=schedule`, icons: [{ src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' }] },
        ],
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        // The Agora SDKs are ~3 MB and only load when a voice call starts, which needs the network anyway.
        globIgnores: ['**/assets/agora-*.js', '**/assets/AgoraRTC_N-*.js'],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
      devOptions: { enabled: false },
    }),
  ],
})
