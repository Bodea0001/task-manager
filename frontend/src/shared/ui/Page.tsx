import CircleDashed from 'lucide-solid/icons/circle-dashed'
import { type ParentProps } from 'solid-js'

interface PageProps extends ParentProps {
  description: string
  title: string
}

export function Page(props: PageProps) {
  return (
    <section class="page">
      <header class="page-header">
        <div>
          <h1 class="page-title">{props.title}</h1>
          <p class="page-description">{props.description}</p>
        </div>
      </header>
      <div class="page-content">{props.children}</div>
    </section>
  )
}

export function EmptyState(props: { message: string; title: string }) {
  return (
    <div class="empty-state">
      <div>
        <span class="empty-state-icon" aria-hidden="true">
          <CircleDashed size={21} strokeWidth={1.8} />
        </span>
        <h2>{props.title}</h2>
        <p>{props.message}</p>
      </div>
    </div>
  )
}
