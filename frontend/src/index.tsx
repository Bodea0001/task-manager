/* @refresh reload */
import '@fontsource-variable/inter/index.css'
import { render } from 'solid-js/web'

import { App } from '@/app/App'
import '@/app/styles/global.css'
import { initializeI18n } from '@/shared/i18n/config'
import { initializeTheme } from '@/shared/theme/ThemeProvider'

const root = document.getElementById('root')

if (root === null) {
  throw new Error('Application root element was not found')
}

initializeTheme()
await initializeI18n()
render(() => <App />, root)
