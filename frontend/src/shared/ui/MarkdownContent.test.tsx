import { render, screen } from '@solidjs/testing-library'
import { describe, expect, it } from 'vitest'

import { MarkdownContent } from '@/shared/ui/MarkdownContent'

describe('Markdown content', () => {
  it('renders formatting while removing executable markup', () => {
    render(() => (
      <MarkdownContent
        source={'**Important** <img src="x" onerror="alert(1)">'}
      />
    ))

    expect(screen.getByText('Important').tagName).toBe('STRONG')
    expect(screen.getByRole('img')).not.toHaveAttribute('onerror')
  })
})
