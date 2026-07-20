/// <reference types="vitest/config" />

import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import solid from 'vite-plugin-solid'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, '.', '')

  return {
    plugins: [
      solid(),
      VitePWA({
        registerType: 'autoUpdate',
        pwaAssets: {
          image: 'public/favicon.svg',
          preset: 'minimal-2023',
          injectThemeColor: false,
          overrideManifestIcons: true,
        },
        manifest: {
          id: '/',
          name: 'Task Manager',
          short_name: 'Task Manager',
          description: 'Tasks, schedules, recurring work, and AI-assisted planning.',
          start_url: '/',
          scope: '/',
          display: 'standalone',
          background_color: '#f5f6fa',
          theme_color: '#4967d8',
          categories: ['productivity'],
          shortcuts: [
            { name: 'Tasks', short_name: 'Tasks', url: '/' },
            { name: 'Calendar', short_name: 'Calendar', url: '/calendar' },
            { name: 'Chat', short_name: 'Chat', url: '/chat' },
          ],
        },
        workbox: {
          cleanupOutdatedCaches: true,
          navigateFallback: '/index.html',
          navigateFallbackDenylist: [/^\/api(?:\/|$)/, /^\/health(?:\/|$)/],
          globPatterns: ['**/*.{css,html,ico,js,png,svg}'],
        },
      }),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: environment.VITE_DEV_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: false,
        },
        '/health': {
          target: environment.VITE_DEV_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: false,
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
