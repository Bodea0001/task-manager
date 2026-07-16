const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/** Keeps sequential keyboard focus inside an open modal surface. */
export function trapFocus(event: KeyboardEvent, container: HTMLElement) {
  if (event.key !== 'Tab') return
  const focusable = [...container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)]
    .filter(isElementVisible)
  if (focusable.length === 0) {
    event.preventDefault()
    container.focus()
    return
  }

  const first = focusable[0]
  const last = focusable.at(-1)!
  const activeElement = document.activeElement
  if (event.shiftKey && (activeElement === first || !container.contains(activeElement))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

/** Implements the horizontal ARIA tabs keyboard interaction pattern. */
export function handleHorizontalTabListKeyDown(
  event: KeyboardEvent,
  tabList: HTMLElement,
) {
  const tabs = [...tabList.querySelectorAll<HTMLElement>('[role="tab"]')].filter(
    (tab) => !tab.hasAttribute('disabled') && isElementVisible(tab),
  )
  const currentIndex = tabs.findIndex((tab) => tab === event.target)
  if (currentIndex < 0 || tabs.length === 0) return

  let nextIndex: number | undefined
  if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length
  if (event.key === 'ArrowLeft') {
    nextIndex = (currentIndex - 1 + tabs.length) % tabs.length
  }
  if (event.key === 'Home') nextIndex = 0
  if (event.key === 'End') nextIndex = tabs.length - 1
  if (nextIndex === undefined) return

  event.preventDefault()
  tabs[nextIndex].focus()
  tabs[nextIndex].click()
}

function isElementVisible(element: HTMLElement) {
  if (
    element.hidden ||
    element.closest('[aria-hidden="true"], [inert]') !== null
  ) {
    return false
  }
  const style = window.getComputedStyle(element)
  return style.display !== 'none' && style.visibility !== 'hidden'
}
