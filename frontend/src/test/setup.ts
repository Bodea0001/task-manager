import '@testing-library/jest-dom/vitest'

import { cleanup } from '@solidjs/testing-library'
import { afterEach } from 'vitest'

import { initializeI18n } from '@/shared/i18n/config'

afterEach(cleanup)

await initializeI18n()
