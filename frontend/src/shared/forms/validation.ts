export type InputValidationIssue =
  | { code: 'invalid_email' }
  | { code: 'invalid_value' }
  | { code: 'required' }
  | { code: 'too_long'; limit: number }
  | { code: 'too_short'; limit: number }

export function getInputValidationIssue(
  input: HTMLInputElement,
): InputValidationIssue | undefined {
  if (input.required && input.value.length === 0) {
    return { code: 'required' }
  }
  if (input.validity.typeMismatch) {
    return { code: input.type === 'email' ? 'invalid_email' : 'invalid_value' }
  }
  if (input.validity.patternMismatch || input.validity.badInput) {
    return { code: 'invalid_value' }
  }
  if (
    input.value.length > 0 &&
    input.minLength >= 0 &&
    input.value.length < input.minLength
  ) {
    return { code: 'too_short', limit: input.minLength }
  }
  if (input.maxLength >= 0 && input.value.length > input.maxLength) {
    return { code: 'too_long', limit: input.maxLength }
  }
  return undefined
}
