import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { createEffect } from 'solid-js'

import './markdown-content.css'

export function MarkdownContent(props: { source: string }) {
  let container!: HTMLDivElement

  createEffect(() => {
    const html = marked.parse(props.source, {
      async: false,
      breaks: true,
      gfm: true,
    })
    const fragment = DOMPurify.sanitize(html, {
      FORBID_ATTR: ['style'],
      FORBID_TAGS: ['style'],
      RETURN_DOM_FRAGMENT: true,
      USE_PROFILES: { html: true },
    })
    container.replaceChildren(fragment)
  })

  return <div ref={container} class="markdown-content" />
}
