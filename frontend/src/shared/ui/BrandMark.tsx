import ListChecks from 'lucide-solid/icons/list-checks'
import Sparkle from 'lucide-solid/icons/sparkle'

import './brand-mark.css'

/** Product mark combining structured tasks with assistant-supported actions. */
export function BrandMark() {
  return (
    <span class="brand-mark" aria-hidden="true">
      <ListChecks class="brand-mark__tasks" size={19} strokeWidth={2.15} />
      <Sparkle class="brand-mark__sparkle" size={8} strokeWidth={2} />
    </span>
  )
}
