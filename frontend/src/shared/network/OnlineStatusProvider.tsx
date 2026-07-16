import {
  createContext,
  createSignal,
  onCleanup,
  onMount,
  type Accessor,
  type ParentProps,
  useContext,
} from 'solid-js'

interface OnlineStatusContextValue {
  isOnline: Accessor<boolean>
}

const OnlineStatusContext = createContext<OnlineStatusContextValue>()

export function OnlineStatusProvider(props: ParentProps) {
  const [isOnline, setOnline] = createSignal(navigator.onLine)

  onMount(() => {
    const handleOnline = () => setOnline(true)
    const handleOffline = () => setOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    onCleanup(() => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    })
  })

  return (
    <OnlineStatusContext.Provider value={{ isOnline }}>
      {props.children}
    </OnlineStatusContext.Provider>
  )
}

export function useOnlineStatus(): OnlineStatusContextValue {
  const context = useContext(OnlineStatusContext)
  if (context === undefined) {
    throw new Error('useOnlineStatus must be used within OnlineStatusProvider')
  }
  return context
}
