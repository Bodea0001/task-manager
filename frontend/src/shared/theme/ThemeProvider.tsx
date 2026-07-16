import {
  createContext,
  createEffect,
  createSignal,
  onCleanup,
  onMount,
  type Accessor,
  type ParentProps,
  useContext,
} from 'solid-js'

export type ThemeMode = 'dark' | 'light' | 'system'
export type ResolvedTheme = Exclude<ThemeMode, 'system'>

interface ThemeContextValue {
  mode: Accessor<ThemeMode>
  resolvedTheme: Accessor<ResolvedTheme>
  setMode: (mode: ThemeMode) => void
}

const THEME_STORAGE_KEY = 'task-manager-theme'
const DARK_SCHEME_QUERY = '(prefers-color-scheme: dark)'
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'
const ThemeContext = createContext<ThemeContextValue>()

interface ViewTransitionHandle {
  finished: Promise<void>
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (
    updateCallback: () => void | Promise<void>,
  ) => ViewTransitionHandle
}

export function initializeTheme(): void {
  const mode = readStoredTheme()
  applyTheme(mode, systemPrefersDark())
}

export function ThemeProvider(props: ParentProps) {
  const mediaQuery = getDarkSchemeMediaQuery()
  const [mode, setMode] = createSignal<ThemeMode>(readStoredTheme())
  const [systemDark, setSystemDark] = createSignal(mediaQuery?.matches ?? false)
  const resolvedTheme = (): ResolvedTheme => {
    return resolveTheme(mode(), systemDark())
  }
  const changeMode = (nextMode: ThemeMode) => {
    if (nextMode === mode()) return
    const updateMode = () => setMode(nextMode)
    if (resolveTheme(nextMode, systemDark()) === resolvedTheme()) {
      updateMode()
      return
    }
    runThemeTransition(updateMode)
  }

  createEffect(() => {
    const nextMode = mode()
    applyTheme(nextMode, systemDark())
    storeTheme(nextMode)
  })

  onMount(() => {
    if (mediaQuery === undefined) return
    const handleChange = (event: MediaQueryListEvent) => {
      if (mode() === 'system' && event.matches !== systemDark()) {
        runThemeTransition(() => setSystemDark(event.matches))
        return
      }
      setSystemDark(event.matches)
    }
    mediaQuery.addEventListener('change', handleChange)
    onCleanup(() => mediaQuery.removeEventListener('change', handleChange))
  })

  return (
    <ThemeContext.Provider value={{ mode, resolvedTheme, setMode: changeMode }}>
      {props.children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}

function applyTheme(mode: ThemeMode, systemDark: boolean): void {
  const resolved = resolveTheme(mode, systemDark)
  document.documentElement.dataset.theme = mode
  document.documentElement.style.colorScheme = resolved
  document
    .querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    ?.setAttribute('content', resolved === 'dark' ? '#24262a' : '#f5f6fa')
}

function resolveTheme(mode: ThemeMode, systemDark: boolean): ResolvedTheme {
  return mode === 'system' ? (systemDark ? 'dark' : 'light') : mode
}

function runThemeTransition(updateTheme: () => void): void {
  const transitionDocument = document as ViewTransitionDocument
  if (
    transitionDocument.startViewTransition === undefined ||
    window.matchMedia(REDUCED_MOTION_QUERY).matches
  ) {
    updateTheme()
    return
  }

  const transition = transitionDocument.startViewTransition(async () => {
    updateTheme()
    await Promise.resolve()
  })
  void transition.finished.catch(() => undefined)
}

function readStoredTheme(): ThemeMode {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return isThemeMode(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

function storeTheme(mode: ThemeMode): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode)
  } catch {
    // Theme selection remains active for the current page when storage is unavailable.
  }
}

function systemPrefersDark(): boolean {
  return getDarkSchemeMediaQuery()?.matches ?? false
}

function getDarkSchemeMediaQuery(): MediaQueryList | undefined {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia(DARK_SCHEME_QUERY)
    : undefined
}

function isThemeMode(value: string | null): value is ThemeMode {
  return value === 'dark' || value === 'light' || value === 'system'
}
