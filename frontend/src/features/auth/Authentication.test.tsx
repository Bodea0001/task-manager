import { fireEvent, render, screen, waitFor } from '@solidjs/testing-library'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from '@/app/App'
import { clearAuthSession } from '@/shared/auth/session'
import { changeLocale } from '@/shared/i18n/config'

beforeEach(async () => {
  clearAuthSession()
  await changeLocale('en')
  window.history.replaceState({}, '', '/')
})

afterEach(() => {
  clearAuthSession()
  vi.unstubAllGlobals()
})

describe('authentication', () => {
  it('protects the workspace and signs a user in', async () => {
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input] = args
      const url = String(input)
      if (url.endsWith('/auth/login')) {
        return Promise.resolve(jsonResponse({
          access_token: 'access-token',
          token_type: 'bearer',
        }))
      }
      if (url.endsWith('/users/me')) {
        return Promise.resolve(jsonResponse({
          user_id: 'user-id',
          first_name: 'Alex',
          last_name: 'Morgan',
          middle_name: null,
          email: 'alex@example.com',
          email_verified: true,
        }))
      }
      if (url.endsWith('/tasks')) {
        return Promise.resolve(jsonResponse({ tasks: [], next_offset: null }))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(() => <App />)

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeVisible()
    expect(window.location.pathname).toBe('/login')
    await fireEvent.input(screen.getByLabelText('Email'), {
      target: { value: 'alex@example.com' },
    })
    await fireEvent.input(screen.getByLabelText('Password'), {
      target: { value: 'correct-password' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Tasks' })).toBeVisible()
    expect(window.location.pathname).toBe('/')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/login',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('shows validation messages in the selected interface language', async () => {
    await changeLocale('ru')
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(() => <App />)

    const emailInput = await screen.findByLabelText('Электронная почта')
    await fireEvent.input(emailInput, {
      target: { value: 'somemail.com' },
    })
    await fireEvent.input(screen.getByLabelText('Пароль'), {
      target: { value: 'correct-password' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Войти' }))

    expect(
      screen.getByText('Введите корректный адрес электронной почты.'),
    ).toBeVisible()
    expect(emailInput).toHaveAttribute('aria-invalid', 'true')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('keeps submitted values and associates server validation with its field', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(
        String(input).endsWith('/auth/login')
          ? jsonResponse(
              {
                code: 'request_validation_error',
                message: 'Request validation failed',
                request_id: 'support-request-id',
                details: [
                  {
                    location: ['body', 'email'],
                    message: 'This email cannot be used',
                    type: 'value_error',
                  },
                ],
              },
              422,
            )
          : jsonResponse({}, 404),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(() => <App />)

    const emailInput = await screen.findByLabelText('Email')
    await fireEvent.input(emailInput, {
      target: { value: 'alex@example.com' },
    })
    await fireEvent.input(screen.getByLabelText('Password'), {
      target: { value: 'correct-password' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('This email cannot be used')).toBeVisible()
    expect(emailInput).toHaveAttribute('aria-invalid', 'true')
    expect(emailInput).toHaveValue('alex@example.com')
    await fireEvent.click(screen.getByText('Technical details'))
    expect(screen.getByText('Request ID: support-request-id')).toBeVisible()
  })

  it('keeps browser password generation enabled during registration', async () => {
    render(() => <App />)

    await fireEvent.click(
      await screen.findByRole('link', { name: 'Create an account' }),
    )
    expect(
      await screen.findByRole('heading', { name: 'Create an account' }),
    ).toBeVisible()

    await waitFor(() =>
      expect(screen.getByLabelText(/^Password/)).toHaveAttribute(
        'autocomplete',
        'new-password',
      ),
    )
    const passwordInput = screen.getByLabelText(/^Password/)

    expect(passwordInput).toHaveAttribute('type', 'password')
    expect(passwordInput).toHaveAttribute('autocomplete', 'new-password')
  })

  it('omits a blank optional name from registration data', async () => {
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input] = args
      const url = String(input)
      if (url.endsWith('/auth/register')) {
        return Promise.resolve(jsonResponse({
          access_token: 'access-token',
          token_type: 'bearer',
        }))
      }
      if (url.endsWith('/users/me')) {
        return Promise.resolve(jsonResponse({
          user_id: 'user-id',
          first_name: 'Alex',
          last_name: 'Morgan',
          middle_name: null,
          email: 'alex@example.com',
          email_verified: true,
        }))
      }
      return Promise.resolve(jsonResponse({ tasks: [], next_offset: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(() => <App />)

    await fireEvent.click(
      await screen.findByRole('link', { name: 'Create an account' }),
    )
    await screen.findByRole('heading', { name: 'Create an account' })
    await fireEvent.input(screen.getByLabelText('First name'), {
      target: { value: 'Alex' },
    })
    await fireEvent.input(screen.getByLabelText('Last name'), {
      target: { value: 'Morgan' },
    })
    await fireEvent.input(screen.getByLabelText(/Middle name/), {
      target: { value: '   ' },
    })
    await fireEvent.input(screen.getByLabelText('Email'), {
      target: { value: 'alex@example.com' },
    })
    await fireEvent.input(screen.getByLabelText(/^Password/), {
      target: { value: 'correct-password' },
    })
    await fireEvent.click(
      screen.getByRole('button', { name: 'Create account' }),
    )

    expect(await screen.findByRole('heading', { name: 'Tasks' })).toBeVisible()
    const registrationCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith('/auth/register'),
    )
    expect(JSON.parse(String(registrationCall?.[1]?.body))).toEqual({
      email: 'alex@example.com',
      first_name: 'Alex',
      last_name: 'Morgan',
      password: 'correct-password',
    })
  })

  it('updates only changed profile fields and can clear the middle name', async () => {
    let currentUser = {
      user_id: 'user-id',
      first_name: 'Alex',
      last_name: 'Morgan',
      middle_name: 'Jordan',
      email: 'alex@example.com',
      email_verified: true,
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (url.endsWith('/auth/login')) {
        return Promise.resolve(jsonResponse({
          access_token: 'access-token',
          token_type: 'bearer',
        }))
      }
      if (url.endsWith('/users/me') && init?.method === 'PATCH') {
        const changes = JSON.parse(String(init.body))
        currentUser = { ...currentUser, ...changes }
        return Promise.resolve(jsonResponse(currentUser))
      }
      if (url.endsWith('/users/me')) return Promise.resolve(jsonResponse(currentUser))
      if (url.endsWith('/tasks')) {
        return Promise.resolve(jsonResponse({ tasks: [], conflicts: [] }))
      }
      if (url.includes('/chats')) {
        return Promise.resolve(jsonResponse({ chats: [], next_offset: null }))
      }
      return Promise.resolve(jsonResponse({}, 404))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(() => <App />)

    await screen.findByRole('heading', { name: 'Sign in' })
    await fireEvent.input(screen.getByLabelText('Email'), {
      target: { value: 'alex@example.com' },
    })
    await fireEvent.input(screen.getByLabelText('Password'), {
      target: { value: 'correct-password' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    const settingsLinks = await screen.findAllByRole('link', { name: 'Settings' })
    await fireEvent.click(settingsLinks[0])

    const firstName = await screen.findByLabelText('First name')
    const middleName = screen.getByLabelText(/Middle name/)
    expect(screen.queryByRole('textbox', { name: 'Email' })).not.toBeInTheDocument()
    expect(screen.getByText('Verified')).toBeVisible()
    await fireEvent.input(firstName, { target: { value: '  Alexa  ' } })
    await fireEvent.input(middleName, { target: { value: '   ' } })
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Profile changes saved.')).toBeVisible()
    const updateCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith('/users/me') && init?.method === 'PATCH',
    )
    expect(JSON.parse(String(updateCall?.[1]?.body))).toEqual({
      first_name: 'Alexa',
      middle_name: null,
    })
    expect(screen.getByText('Alexa Morgan')).toBeVisible()
  })
})

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}
