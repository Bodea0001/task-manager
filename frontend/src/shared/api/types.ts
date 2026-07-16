export interface ApiErrorDetail {
  code?: string
  location?: readonly (number | string)[]
  message?: string
  type?: string
}

export interface ApiErrorResponse {
  code: string
  details?: readonly ApiErrorDetail[]
  message: string
  request_id?: string
}
