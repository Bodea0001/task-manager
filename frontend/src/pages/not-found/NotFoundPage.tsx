import { A } from '@solidjs/router'
import ArrowLeft from 'lucide-solid/icons/arrow-left'

import { useI18n } from '@/shared/i18n/I18nProvider'
import { Page } from '@/shared/ui/Page'

export function NotFoundPage() {
  const { t } = useI18n()
  return (
    <Page
      title={t('common.pages.notFound.title')}
      description={t('common.pages.notFound.description')}
    >
      <A class="secondary-button" href="/">
        <ArrowLeft size={16} strokeWidth={2} aria-hidden="true" />
        {t('common.actions.returnToTasks')}
      </A>
    </Page>
  )
}
