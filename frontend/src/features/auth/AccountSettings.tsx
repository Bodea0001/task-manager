import LogOut from 'lucide-solid/icons/log-out'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import UserRound from 'lucide-solid/icons/user-round'
import { createEffect, createMemo, createSignal, Show, type JSX } from 'solid-js'

import { useAuth } from '@/features/auth/AuthProvider'
import type { UpdateUserData } from '@/features/auth/api'
import { ApiError } from '@/shared/api/http'
import {
  clearFormApiField,
  type FormApiError,
  toFormApiError,
} from '@/shared/forms/apiErrors'
import {
  getInputValidationIssue,
  type InputValidationIssue,
} from '@/shared/forms/validation'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import { FormErrorSummary } from '@/shared/ui/FormErrorSummary'

type AccountFieldName = 'email' | 'first_name' | 'last_name' | 'middle_name'
type AccountFieldIssues = Partial<Record<AccountFieldName, InputValidationIssue>>
const accountFieldNames: readonly AccountFieldName[] = [
  'email',
  'first_name',
  'last_name',
  'middle_name',
]

export function AccountSettings() {
  const auth = useAuth()
  const { t } = useI18n()
  const [firstName, setFirstName] = createSignal('')
  const [lastName, setLastName] = createSignal('')
  const [middleName, setMiddleName] = createSignal('')
  const [email, setEmail] = createSignal('')
  const [fieldIssues, setFieldIssues] = createSignal<AccountFieldIssues>({})
  const [errorKey, setErrorKey] = createSignal<TranslationKey>()
  const [apiError, setApiError] = createSignal<FormApiError>()
  const [isSubmitting, setSubmitting] = createSignal(false)
  const [isSaved, setSaved] = createSignal(false)

  const resetForm = () => {
    const user = auth.user()
    if (user === undefined) return
    setFirstName(user.first_name)
    setLastName(user.last_name)
    setMiddleName(user.middle_name || '')
    setEmail(user.email)
    setFieldIssues({})
    setErrorKey()
    setApiError()
    setSaved(false)
  }

  createEffect(() => {
    auth.user()
    resetForm()
  })

  const updateData = createMemo<UpdateUserData>(() => {
    const user = auth.user()
    if (user === undefined) return {}

    const data: UpdateUserData = {}
    const normalizedFirstName = normalizeName(firstName())
    const normalizedLastName = normalizeName(lastName())
    const normalizedMiddleName = normalizeOptionalName(middleName())
    const normalizedEmail = email().trim().toLowerCase()

    if (normalizedFirstName !== user.first_name) data.first_name = normalizedFirstName
    if (normalizedLastName !== user.last_name) data.last_name = normalizedLastName
    if (normalizedMiddleName !== user.middle_name) data.middle_name = normalizedMiddleName
    if (normalizedEmail !== user.email) data.email = normalizedEmail
    return data
  })
  const hasChanges = () => Object.keys(updateData()).length > 0

  const clearFeedback = (fieldName: AccountFieldName) => {
    setFieldIssues((current) => {
      if (current[fieldName] === undefined) return current
      const next = { ...current }
      delete next[fieldName]
      return next
    })
    setErrorKey()
    setApiError((current) => clearFormApiField(current, fieldName))
    setSaved(false)
  }

  const submit: JSX.EventHandler<HTMLFormElement, SubmitEvent> = (event) => {
    event.preventDefault()
    if (!validateForm(event.currentTarget, setFieldIssues)) return
    if (!hasChanges()) return
    void save(updateData())
  }

  const save = async (data: UpdateUserData) => {
    setSubmitting(true)
    setErrorKey()
    setApiError()
    setSaved(false)
    try {
      await auth.updateUser(data)
      setSaved(true)
    } catch (error) {
      setApiError(toFormApiError(error, { fields: accountFieldNames }))
      setErrorKey(accountErrorKey(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section class="settings-section" aria-labelledby="account-settings-title">
      <header class="settings-section-header">
        <span class="settings-section-icon" aria-hidden="true">
          <UserRound size={19} strokeWidth={1.9} />
        </span>
        <div>
          <h2 id="account-settings-title">{t('auth.account.title')}</h2>
          <p>{t('auth.account.description')}</p>
        </div>
      </header>

      <form class="account-form" novalidate onSubmit={submit}>
        <div class="account-name-fields">
          <AccountField
            name="first_name"
            label={t('auth.fields.firstName')}
            autocomplete="given-name"
            maxlength={250}
            required
            value={firstName()}
            issue={fieldIssues().first_name}
            serverError={apiError()?.fieldErrors.first_name}
            onInput={(value) => {
              setFirstName(value)
              clearFeedback('first_name')
            }}
          />
          <AccountField
            name="last_name"
            label={t('auth.fields.lastName')}
            autocomplete="family-name"
            maxlength={250}
            required
            value={lastName()}
            issue={fieldIssues().last_name}
            serverError={apiError()?.fieldErrors.last_name}
            onInput={(value) => {
              setLastName(value)
              clearFeedback('last_name')
            }}
          />
        </div>
        <AccountField
          name="middle_name"
          label={`${t('auth.fields.middleName')} (${t('auth.fields.optional')})`}
          autocomplete="additional-name"
          maxlength={250}
          value={middleName()}
          issue={fieldIssues().middle_name}
          serverError={apiError()?.fieldErrors.middle_name}
          onInput={(value) => {
            setMiddleName(value)
            clearFeedback('middle_name')
          }}
        />
        <AccountField
          name="email"
          type="email"
          label={t('auth.fields.email')}
          autocomplete="email"
          maxlength={320}
          required
          value={email()}
          issue={fieldIssues().email}
          serverError={apiError()?.fieldErrors.email}
          onInput={(value) => {
            setEmail(value)
            clearFeedback('email')
          }}
        />

        <Show when={errorKey() !== undefined}>
          <FormErrorSummary
            error={apiError()}
            message={t(errorKey()!)}
            fieldLabels={{
              email: t('auth.fields.email'),
              first_name: t('auth.fields.firstName'),
              last_name: t('auth.fields.lastName'),
              middle_name: t('auth.fields.middleName'),
            }}
          />
        </Show>
        <Show when={isSaved()}>
          <p class="account-form-message account-form-message--success" role="status">
            {t('auth.account.saved')}
          </p>
        </Show>

        <div class="account-form-actions">
          <button
            type="button"
            class="secondary-button"
            disabled={!hasChanges() || isSubmitting()}
            onClick={resetForm}
          >
            {t('common.actions.cancel')}
          </button>
          <button
            type="submit"
            class="primary-button"
            disabled={!hasChanges() || isSubmitting()}
            aria-busy={isSubmitting()}
          >
            <Show when={isSubmitting()}>
              <LoaderCircle class="spin" size={16} aria-hidden="true" />
            </Show>
            {t(isSubmitting() ? 'auth.account.saving' : 'auth.account.save')}
          </button>
        </div>
      </form>

      <div class="account-session">
        <div>
          <strong>
            {[auth.user()?.first_name, auth.user()?.last_name]
              .filter(Boolean)
              .join(' ')}
          </strong>
          <span>
            {t('auth.account.signedInAs', { email: auth.user()?.email || '' })}
          </span>
        </div>
        <button
          type="button"
          class="secondary-button"
          onClick={() => void auth.logout()}
        >
          <LogOut size={16} strokeWidth={1.9} aria-hidden="true" />
          {t('auth.account.signOut')}
        </button>
      </div>
    </section>
  )
}

function AccountField(props: {
  autocomplete: string
  issue?: InputValidationIssue
  serverError?: string
  label: string
  maxlength: number
  name: AccountFieldName
  onInput: (value: string) => void
  required?: boolean
  type?: string
  value: string
}) {
  const { t } = useI18n()
  const inputId = () => `account-${props.name.replaceAll('_', '-')}`
  const errorId = () => `${inputId()}-error`
  return (
    <label class="account-field">
      <span>{props.label}</span>
      <input
        id={inputId()}
        name={props.name}
        type={props.type || 'text'}
        autocomplete={props.autocomplete}
        maxlength={props.maxlength}
        required={props.required}
        value={props.value}
        aria-invalid={props.issue !== undefined || props.serverError !== undefined}
        aria-describedby={
          props.issue === undefined && props.serverError === undefined
            ? undefined
            : errorId()
        }
        onInput={(event) => props.onInput(event.currentTarget.value)}
      />
      <Show when={props.issue || props.serverError}>
        {(issue) => (
          <small id={errorId()}>
            {formatAccountFieldError(t, issue())}
          </small>
        )}
      </Show>
    </label>
  )
}

function validateForm(
  form: HTMLFormElement,
  setIssues: (issues: AccountFieldIssues) => void,
): boolean {
  const issues: AccountFieldIssues = {}
  let firstInvalidInput: HTMLInputElement | undefined

  for (const element of form.elements) {
    if (!(element instanceof HTMLInputElement) || !isAccountFieldName(element.name)) {
      continue
    }
    const issue = getInputValidationIssue(element) || requiredTrimmedIssue(element)
    if (issue !== undefined) {
      issues[element.name] = issue
      firstInvalidInput ??= element
    }
  }

  setIssues(issues)
  firstInvalidInput?.focus()
  return firstInvalidInput === undefined
}

function requiredTrimmedIssue(input: HTMLInputElement): InputValidationIssue | undefined {
  return input.required && input.value.trim().length === 0
    ? { code: 'required' }
    : undefined
}

function isAccountFieldName(value: string): value is AccountFieldName {
  return ['email', 'first_name', 'last_name', 'middle_name'].includes(value)
}

function normalizeName(value: string): string {
  return value.trim().split(/\s+/).filter(Boolean).join(' ')
}

function normalizeOptionalName(value: string): string | null {
  return normalizeName(value) || null
}

function formatValidationIssue(
  t: ReturnType<typeof useI18n>['t'],
  issue: InputValidationIssue,
): string {
  const keys: Record<InputValidationIssue['code'], TranslationKey> = {
    invalid_email: 'common.validation.invalidEmail',
    invalid_value: 'common.validation.invalidValue',
    required: 'common.validation.required',
    too_long: 'common.validation.tooLong',
    too_short: 'common.validation.tooShort',
  }
  return t(keys[issue.code], 'limit' in issue ? { count: issue.limit } : undefined)
}

function formatAccountFieldError(
  t: ReturnType<typeof useI18n>['t'],
  error: InputValidationIssue | string,
): string {
  return typeof error === 'string' ? error : formatValidationIssue(t, error)
}

function accountErrorKey(error: unknown): TranslationKey {
  if (!(error instanceof ApiError)) return 'auth.errors.unavailable'
  if (error.code === 'email_already_exists') return 'auth.errors.emailExists'
  if (error.code === 'request_validation_error') return 'auth.errors.validation'
  return 'auth.errors.generic'
}
