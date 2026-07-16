export function readFormString(form: FormData, name: string): string {
  const value = form.get(name)
  return typeof value === 'string' ? value : ''
}

export function readOptionalFormString(
  form: FormData,
  name: string,
): string | undefined {
  const value = readFormString(form, name)
  return value.trim().length === 0 ? undefined : value
}
