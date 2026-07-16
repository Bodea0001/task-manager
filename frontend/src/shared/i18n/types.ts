import type { TOptions } from 'i18next'

import type { enTranslation } from '@/shared/i18n/locales/en'

type LeafPath<T, Prefix extends string = ''> = {
  [Key in keyof T & string]: T[Key] extends string
    ? `${Prefix}${Key}`
    : LeafPath<T[Key], `${Prefix}${Key}.`>
}[keyof T & string]

type PluralSuffix = '_zero' | '_one' | '_two' | '_few' | '_many' | '_other'
type NormalizePluralKey<Key extends string> =
  Key extends `${infer Base}${PluralSuffix}` ? Base : Key

export type Locale = 'en' | 'ru'
export type TextDirection = 'ltr' | 'rtl'
export type TranslationKey = NormalizePluralKey<LeafPath<typeof enTranslation>>
export type TranslationOptions = TOptions & Record<string, unknown>

export interface LocaleMetadata {
  code: Locale
  direction: TextDirection
  nativeName: string
}
