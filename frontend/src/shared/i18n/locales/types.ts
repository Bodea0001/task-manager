export type DictionaryShape<T> = {
  readonly [Key in keyof T]: T[Key] extends string
    ? string
    : DictionaryShape<T[Key]>
}
