const DEFAULT_API_BASE_URL = '/api/v1'

export const environment = Object.freeze({
  apiBaseUrl: normalizeBaseUrl(
    import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL,
  ),
})

function normalizeBaseUrl(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value
}
