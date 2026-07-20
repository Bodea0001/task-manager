import { A } from '@solidjs/router'
import Eye from 'lucide-solid/icons/eye'
import EyeOff from 'lucide-solid/icons/eye-off'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import { createSignal, For, Show, type JSX } from 'solid-js'

import './auth.css'

import { useAuth } from '@/features/auth/AuthProvider'
import { ApiError } from '@/shared/api/http'
import {
  readFormString,
  readOptionalFormString,
} from '@/shared/forms/formData'
import {
  clearFormApiField,
  type FormApiError,
  toFormApiError,
} from '@/shared/forms/apiErrors'
import {
  getInputValidationIssue,
  type InputValidationIssue,
} from '@/shared/forms/validation'
import { supportedLocales } from '@/shared/i18n/config'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type {
  TranslationKey,
  TranslationOptions,
} from '@/shared/i18n/types'
import { BrandMark } from '@/shared/ui/BrandMark'
import { FormErrorSummary } from '@/shared/ui/FormErrorSummary'

type AuthMode = 'login' | 'register'
type AuthFieldName =
  | 'email'
  | 'first_name'
  | 'last_name'
  | 'middle_name'
  | 'password'
type AuthFieldIssue =
  | InputValidationIssue
  | { code: 'password_whitespace' }
type AuthFieldIssues = Partial<Record<AuthFieldName, AuthFieldIssue>>
interface AuthErrorPresentation {
  key: TranslationKey
  options?: TranslationOptions
}

const authFieldNames: readonly AuthFieldName[] = [
  'email',
  'first_name',
  'last_name',
  'middle_name',
  'password',
]

export function AuthForm(props: { mode: AuthMode }) {
  const auth = useAuth()
  const { locale, setLocale, t } = useI18n()
  const [isSubmitting, setSubmitting] = createSignal(false)
  const [isPasswordVisible, setPasswordVisible] = createSignal(false)
  const [errorPresentation, setErrorPresentation] =
    createSignal<AuthErrorPresentation>()
  const [apiError, setApiError] = createSignal<FormApiError>()
  const [fieldIssues, setFieldIssues] = createSignal<AuthFieldIssues>({})
  const isRegistration = () => props.mode === 'register'

  const handleSubmit: JSX.EventHandler<HTMLFormElement, SubmitEvent> = (
    event,
  ) => {
    event.preventDefault()
    const form = event.currentTarget
    if (!validateForm(form)) {
      return
    }
    void submit(new FormData(form))
  }

  const validateForm = (form: HTMLFormElement): boolean => {
    const issues: AuthFieldIssues = {}
    let firstInvalidInput: HTMLInputElement | undefined

    for (const element of form.elements) {
      if (!(element instanceof HTMLInputElement) || !isAuthFieldName(element.name)) {
        continue
      }
      const issue = getAuthFieldIssue(element, isRegistration())
      if (issue !== undefined) {
        issues[element.name] = issue
        firstInvalidInput ??= element
      }
    }

    setFieldIssues(issues)
    firstInvalidInput?.focus()
    return firstInvalidInput === undefined
  }

  const clearFieldIssue = (name: AuthFieldName) => {
    setFieldIssues((current) => {
      if (current[name] === undefined) {
        return current
      }
      const next = { ...current }
      delete next[name]
      return next
    })
    setErrorPresentation()
    setApiError((current) => clearFormApiField(current, name))
  }

  const submit = async (form: FormData) => {
    setSubmitting(true)
    setErrorPresentation()
    setApiError()

    try {
      const email = readFormString(form, 'email')
      const password = readFormString(form, 'password')
      if (isRegistration()) {
        const middleName = readOptionalFormString(form, 'middle_name')
        await auth.register({
          email,
          password,
          first_name: readFormString(form, 'first_name'),
          last_name: readFormString(form, 'last_name'),
          ...(middleName === undefined ? {} : { middle_name: middleName }),
        })
      } else {
        await auth.login({ email, password })
      }
    } catch (error) {
      setApiError(toFormApiError(error, { fields: authFieldNames }))
      setErrorPresentation(getAuthErrorPresentation(error))
    } finally {
      setSubmitting(false)
    }
  }

  const passwordToggleLabel = () =>
    t(
      isPasswordVisible()
        ? 'auth.fields.hidePassword'
        : 'auth.fields.showPassword',
    )

  return (
    <main class="auth-page">
      <section class="auth-panel" aria-labelledby="auth-title">
        <div class="auth-topbar">
          <div class="auth-brand" aria-hidden="true">
            <BrandMark />
            {t('common.appName')}
          </div>
          <div class="auth-languages" aria-label={t('common.language.title')}>
            <For each={supportedLocales}>
              {(option) => (
                <button
                  type="button"
                  classList={{ 'auth-language--active': locale() === option.code }}
                  aria-label={option.nativeName}
                  aria-pressed={locale() === option.code}
                  title={option.nativeName}
                  onClick={() => void setLocale(option.code)}
                >
                  {option.code.toUpperCase()}
                </button>
              )}
            </For>
          </div>
        </div>

        <header class="auth-header">
          <h1 id="auth-title">
            {t(isRegistration() ? 'auth.register.title' : 'auth.login.title')}
          </h1>
          <p>
            {t(
              isRegistration()
                ? 'auth.register.description'
                : 'auth.login.description',
            )}
          </p>
        </header>

        <form class="auth-form" novalidate onSubmit={handleSubmit}>
          <Show when={isRegistration()}>
            <div class="auth-name-fields">
              <AuthField
                name="first_name"
                label={t('auth.fields.firstName')}
                autocomplete="given-name"
                maxlength={250}
                required
                issue={fieldIssues().first_name}
                serverError={apiError()?.fieldErrors.first_name}
                onInput={() => clearFieldIssue('first_name')}
              />
              <AuthField
                name="last_name"
                label={t('auth.fields.lastName')}
                autocomplete="family-name"
                maxlength={250}
                required
                issue={fieldIssues().last_name}
                serverError={apiError()?.fieldErrors.last_name}
                onInput={() => clearFieldIssue('last_name')}
              />
            </div>
            <AuthField
              name="middle_name"
              label={`${t('auth.fields.middleName')} (${t('auth.fields.optional')})`}
              autocomplete="additional-name"
              maxlength={250}
              issue={fieldIssues().middle_name}
              serverError={apiError()?.fieldErrors.middle_name}
              onInput={() => clearFieldIssue('middle_name')}
            />
          </Show>

          <AuthField
            name="email"
            type="email"
            label={t('auth.fields.email')}
            autocomplete="email"
            required
            issue={fieldIssues().email}
            serverError={apiError()?.fieldErrors.email}
            onInput={() => clearFieldIssue('email')}
          />

          <label class="auth-field">
            <span>{t('auth.fields.password')}</span>
            <span class="password-input">
              <Show
                keyed
                when={
                  isRegistration() ? 'new-password' : 'current-password'
                }
              >
                {(passwordAutocomplete) => (
                  <input
                    id="auth-password"
                    name="password"
                    type={isPasswordVisible() ? 'text' : 'password'}
                    autocomplete={passwordAutocomplete}
                    minlength={
                      passwordAutocomplete === 'new-password' ? 8 : undefined
                    }
                    required
                    aria-invalid={
                      fieldIssues().password !== undefined ||
                      apiError()?.fieldErrors.password !== undefined
                    }
                    aria-describedby={[
                      isRegistration() ? 'auth-password-hint' : undefined,
                      fieldIssues().password !== undefined ||
                      apiError()?.fieldErrors.password !== undefined
                        ? 'auth-password-error'
                        : undefined,
                    ].filter(Boolean).join(' ') || undefined}
                    onInput={() => clearFieldIssue('password')}
                  />
                )}
              </Show>
              <button
                type="button"
                aria-label={passwordToggleLabel()}
                title={passwordToggleLabel()}
                onClick={() => setPasswordVisible((visible) => !visible)}
              >
                <Show when={isPasswordVisible()} fallback={<Eye size={17} />}>
                  <EyeOff size={17} />
                </Show>
              </button>
            </span>
            <Show when={isRegistration()}>
              <small id="auth-password-hint">{t('auth.fields.passwordHint')}</small>
            </Show>
            <Show when={fieldIssues().password || apiError()?.fieldErrors.password}>
              {(issue) => (
                <small id="auth-password-error" class="auth-field-error">
                  {formatAuthFieldError(t, issue())}
                </small>
              )}
            </Show>
          </label>

          <Show when={errorPresentation()}>
            {(presentation) => (
              <FormErrorSummary
                error={apiError()}
                message={t(presentation().key, presentation().options)}
                fieldLabels={{
                  email: t('auth.fields.email'),
                  first_name: t('auth.fields.firstName'),
                  last_name: t('auth.fields.lastName'),
                  middle_name: t('auth.fields.middleName'),
                  password: t('auth.fields.password'),
                }}
              />
            )}
          </Show>

          <button
            type="submit"
            class="primary-button auth-submit"
            disabled={isSubmitting()}
            aria-busy={isSubmitting()}
          >
            <Show
              when={isSubmitting()}
              fallback={t(
                isRegistration() ? 'auth.register.submit' : 'auth.login.submit',
              )}
            >
              <LoaderCircle class="spin" size={17} aria-hidden="true" />
              {t(
                isRegistration()
                  ? 'auth.register.submitting'
                  : 'auth.login.submitting',
              )}
            </Show>
          </button>
        </form>

        <p class="auth-alternative">
          {t(
            isRegistration()
              ? 'auth.register.hasAccount'
              : 'auth.login.noAccount',
          )}{' '}
          <A href={isRegistration() ? '/login' : '/register'}>
            {t(
              isRegistration()
                ? 'auth.register.loginLink'
                : 'auth.login.registerLink',
            )}
          </A>
        </p>
      </section>
    </main>
  )
}

function AuthField(props: {
  autocomplete: string
  label: string
  maxlength?: number
  name: AuthFieldName
  issue?: AuthFieldIssue
  serverError?: string
  onInput: () => void
  required?: boolean
  type?: string
}) {
  const { t } = useI18n()
  const inputId = () => `auth-${props.name.replaceAll('_', '-')}`
  const errorId = () => `${inputId()}-error`

  return (
    <label class="auth-field">
      <span>{props.label}</span>
      <input
        id={inputId()}
        name={props.name}
        type={props.type || 'text'}
        autocomplete={props.autocomplete}
        maxlength={props.maxlength}
        required={props.required}
        aria-invalid={props.issue !== undefined || props.serverError !== undefined}
        aria-describedby={
          props.issue === undefined && props.serverError === undefined
            ? undefined
            : errorId()
        }
        onInput={() => props.onInput()}
      />
      <Show when={props.issue || props.serverError}>
        {(issue) => (
          <small id={errorId()} class="auth-field-error">
            {formatAuthFieldError(t, issue())}
          </small>
        )}
      </Show>
    </label>
  )
}

function getAuthFieldIssue(
  input: HTMLInputElement,
  isRegistration: boolean,
): AuthFieldIssue | undefined {
  const standardIssue = getInputValidationIssue(input)
  if (standardIssue !== undefined) {
    return standardIssue
  }
  if (
    isRegistration &&
    input.name === 'password' &&
    input.value.trim() !== input.value
  ) {
    return { code: 'password_whitespace' }
  }
  if (
    input.required &&
    input.type !== 'password' &&
    input.value.trim().length === 0
  ) {
    return { code: 'required' }
  }
  return undefined
}

function isAuthFieldName(value: string): value is AuthFieldName {
  return ['email', 'first_name', 'last_name', 'middle_name', 'password'].includes(
    value,
  )
}

function formatValidationIssue(
  t: ReturnType<typeof useI18n>['t'],
  issue: AuthFieldIssue,
): string {
  const issueKeys: Record<AuthFieldIssue['code'], TranslationKey> = {
    invalid_email: 'common.validation.invalidEmail',
    invalid_value: 'common.validation.invalidValue',
    password_whitespace: 'auth.validation.passwordWhitespace',
    required: 'common.validation.required',
    too_long: 'common.validation.tooLong',
    too_short: 'common.validation.tooShort',
  }
  return t(
    issueKeys[issue.code],
    'limit' in issue ? { count: issue.limit } : undefined,
  )
}

function formatAuthFieldError(
  t: ReturnType<typeof useI18n>['t'],
  error: AuthFieldIssue | string,
): string {
  return typeof error === 'string' ? error : formatValidationIssue(t, error)
}

function getAuthErrorPresentation(error: unknown): AuthErrorPresentation {
  if (!(error instanceof ApiError)) {
    return { key: 'auth.errors.unavailable' }
  }

  const errorKeys: Partial<Record<string, TranslationKey>> = {
    auth_protection_unavailable: 'auth.errors.protectionUnavailable',
    invalid_credentials: 'auth.errors.invalidCredentials',
    invalid_client_address: 'auth.errors.invalidClientAddress',
    email_already_exists: 'auth.errors.emailExists',
    registration_limit_exceeded: 'auth.errors.registrationLimit',
    request_validation_error: 'auth.errors.validation',
  }

  if (error.code === 'rate_limit_exceeded') {
    const retryAfterSeconds = error.context?.retry_after_seconds
    return {
      key: 'auth.errors.rateLimited',
      options:
        typeof retryAfterSeconds === 'number' &&
        Number.isFinite(retryAfterSeconds) &&
        retryAfterSeconds > 0
          ? { count: Math.ceil(retryAfterSeconds) }
          : undefined,
    }
  }

  return { key: errorKeys[error.code] || 'auth.errors.generic' }
}
