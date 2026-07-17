import { For, Show } from 'solid-js'

import './recurrence-rule-fields.css'

import type {
  RecurrenceBusinessDayPolicy,
  RecurrenceFrequency,
  Weekday,
} from '@/entities/recurrence/model'
import type {
  MonthRuleMode,
  RecurrenceRuleForm,
} from '@/features/recurrence-rules/recurrenceRuleForm'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import { DateTimePicker } from '@/shared/ui/DateTimePicker'
import { SelectField } from '@/shared/ui/SelectField'

const frequencies: readonly RecurrenceFrequency[] = ['daily', 'weekly', 'monthly']
const weekdays: readonly Weekday[] = [1, 2, 3, 4, 5, 6, 7]

const frequencyLabelKeys: Record<RecurrenceFrequency, TranslationKey> = {
  daily: 'recurring.rules.frequency.daily',
  weekly: 'recurring.rules.frequency.weekly',
  monthly: 'recurring.rules.frequency.monthly',
}

const intervalLabelKeys: Record<RecurrenceFrequency, TranslationKey> = {
  daily: 'recurring.rules.interval_daily',
  weekly: 'recurring.rules.interval_weekly',
  monthly: 'recurring.rules.interval_monthly',
}

const weekdayLabelKeys: Record<Weekday, TranslationKey> = {
  1: 'recurring.rules.weekdays.monday',
  2: 'recurring.rules.weekdays.tuesday',
  3: 'recurring.rules.weekdays.wednesday',
  4: 'recurring.rules.weekdays.thursday',
  5: 'recurring.rules.weekdays.friday',
  6: 'recurring.rules.weekdays.saturday',
  7: 'recurring.rules.weekdays.sunday',
}

const weekdayShortLabelKeys: Record<Weekday, TranslationKey> = {
  1: 'recurring.rules.weekdaysShort.monday',
  2: 'recurring.rules.weekdaysShort.tuesday',
  3: 'recurring.rules.weekdaysShort.wednesday',
  4: 'recurring.rules.weekdaysShort.thursday',
  5: 'recurring.rules.weekdaysShort.friday',
  6: 'recurring.rules.weekdaysShort.saturday',
  7: 'recurring.rules.weekdaysShort.sunday',
}

const businessDayPolicies: readonly RecurrenceBusinessDayPolicy[] = [
  'none',
  'next_business_day',
  'previous_business_day',
]

const businessDayPolicyLabelKeys: Record<
  RecurrenceBusinessDayPolicy,
  TranslationKey
> = {
  none: 'recurring.rules.editor.businessDay.none',
  next_business_day: 'recurring.rules.editor.businessDay.next',
  previous_business_day: 'recurring.rules.editor.businessDay.previous',
}

export function recurrenceFieldLabels(
  t: ReturnType<typeof useI18n>['t'],
): Readonly<Record<string, string>> {
  return {
    frequency: t('recurring.rules.editor.frequency'),
    interval: t('recurring.rules.editor.interval'),
    weekdays: t('recurring.rules.editor.weekdays'),
    month_rule_mode: t('recurring.rules.editor.monthRule'),
    month_day: t('recurring.rules.editor.monthDayNumber'),
    ordinal_week: t('recurring.rules.editor.ordinalWeek'),
    ordinal_weekday: t('recurring.rules.editor.ordinalWeekdayName'),
    business_day_policy: t('recurring.rules.editor.businessDay.label'),
    anchor_date: t('recurring.rules.editor.anchorDate'),
    default_time: t('recurring.rules.editor.defaultTime'),
    duration_hours: t('recurring.rules.editor.durationHours'),
    duration_minutes: t('recurring.rules.editor.durationMinutes'),
    end_mode: t('recurring.rules.editor.endMode'),
    repeat_until: t('recurring.rules.editor.repeatUntil'),
    occurrences_limit: t('recurring.rules.editor.occurrencesLimit'),
  }
}

export function RecurrenceRuleFields(props: {
  disabled: boolean
  errors?: Readonly<Record<string, string>>
  form: RecurrenceRuleForm
  isEditing: boolean
  onChange: () => void
}) {
  const { t } = useI18n()

  const toggleWeekday = (weekday: Weekday) => {
    const selected = props.form.weekdays()
    props.form.setWeekdays(
      selected.includes(weekday)
        ? selected.filter((value) => value !== weekday)
        : weekdays.filter((value) => value === weekday || selected.includes(value)),
    )
    props.onChange()
  }

  const cadenceDetails = () => {
    if (props.form.frequency() === 'weekly') {
      return props.form
        .weekdays()
        .map((weekday) => t(weekdayLabelKeys[weekday]))
        .join(', ')
    }
    if (props.form.frequency() === 'monthly') {
      return props.form.monthRuleMode() === 'month_day'
        ? t('recurring.rules.monthRule.monthDay', {
            day: Number(props.form.monthDay()),
          })
        : t('recurring.rules.monthRule.ordinalWeekday', {
            position: t(
              `recurring.rules.editor.ordinal.${props.form.ordinalWeek() === '-1' ? 'last' : `week${props.form.ordinalWeek()}`}` as TranslationKey,
            ),
            weekday: t(weekdayLabelKeys[props.form.ordinalWeekday()]),
          })
    }
    return undefined
  }

  return (
    <>
      <Show
        when={!props.isEditing}
        fallback={
          <div class="recurrence-rule-fixed-cadence">
            <strong>{t(frequencyLabelKeys[props.form.frequency()])}</strong>
            <span>
              {t(intervalLabelKeys[props.form.frequency()], {
                count: Number(props.form.interval()),
              })}
            </span>
            <Show when={cadenceDetails()}>{(details) => <span>{details()}</span>}</Show>
            <p>{t('recurring.rules.editor.fixedCadence')}</p>
          </div>
        }
      >
        <div class="recurrence-rule-fields">
          <SelectField
            name="frequency"
            label={t('recurring.rules.editor.frequency')}
            value={props.form.frequency()}
            disabled={props.disabled}
            error={props.errors?.frequency}
            options={frequencies.map((value) => ({
              label: t(frequencyLabelKeys[value]),
              value,
            }))}
            onChange={(value) => {
              props.form.setFrequency(value)
              props.onChange()
            }}
          />
          <NumberField
            name="interval"
            label={t('recurring.rules.editor.interval')}
            value={props.form.interval()}
            disabled={props.disabled}
            error={props.errors?.interval}
            onChange={props.form.setInterval}
            onEdited={props.onChange}
          />
        </div>

        <Show when={props.form.frequency() === 'weekly'}>
          <fieldset
            class="recurrence-weekday-field"
            aria-invalid={props.errors?.weekdays === undefined ? undefined : 'true'}
            aria-describedby={`recurrence-weekdays-hint${
              props.errors?.weekdays === undefined
                ? ''
                : ' recurrence-weekdays-error'
            }`}
          >
            <legend>{t('recurring.rules.editor.weekdays')}</legend>
            <p id="recurrence-weekdays-hint" class="recurrence-rule-field-hint">
              {t('recurring.rules.editor.weekdaysHint')}
            </p>
            <div>
              <For each={weekdays}>
                {(weekday) => (
                  <button
                    type="button"
                    aria-label={t(weekdayLabelKeys[weekday])}
                    aria-pressed={props.form.weekdays().includes(weekday)}
                    disabled={props.disabled}
                    onClick={() => toggleWeekday(weekday)}
                  >
                    {t(weekdayShortLabelKeys[weekday])}
                  </button>
                )}
              </For>
            </div>
            <Show when={props.errors?.weekdays}>
              {(error) => (
                <small id="recurrence-weekdays-error" class="recurrence-rule-field-error">
                  {error()}
                </small>
              )}
            </Show>
          </fieldset>
        </Show>

        <Show when={props.form.frequency() === 'monthly'}>
          <MonthlyRuleFields {...props} />
        </Show>
      </Show>

      <div class="recurrence-rule-fields">
        <DateTimePicker
          mode="date"
          name="anchor_date"
          label={t('recurring.rules.editor.anchorDate')}
          value={props.form.anchorDate()}
          required
          disabled={props.disabled}
          error={props.errors?.anchor_date}
          onChange={(value) => {
            props.form.setAnchorDate(value)
            props.onChange()
          }}
          onValidityChange={props.form.setAnchorDateValid}
        />
        <DateTimePicker
          mode="time"
          name="default_time"
          label={t(
            props.form.hasDuration()
              ? 'recurring.rules.editor.blockStartTime'
              : 'recurring.rules.editor.deadlineTimeField',
          )}
          value={props.form.defaultTime()}
          required
          disabled={props.disabled}
          error={props.errors?.default_time}
          onChange={(value) => {
            props.form.setDefaultTime(value)
            props.onChange()
          }}
          onValidityChange={props.form.setDefaultTimeValid}
        />
      </div>

      <div class="recurrence-duration">
        <button
          type="button"
          role="switch"
          aria-checked={props.form.hasDuration()}
          disabled={props.disabled}
          onClick={() => {
            props.form.setHasDuration(!props.form.hasDuration())
            props.onChange()
          }}
        >
          <span aria-hidden="true" />
          {t('recurring.rules.editor.addDuration')}
        </button>
        <p>
          {t(
            props.form.hasDuration()
              ? 'recurring.rules.editor.durationActiveHint'
              : 'recurring.rules.editor.durationHint',
          )}
        </p>
        <Show when={props.form.hasDuration()}>
          <div class="recurrence-rule-fields recurrence-duration-fields">
            <NumberField
              name="duration_hours"
              label={t('recurring.rules.editor.durationHours')}
              value={props.form.durationHours()}
              disabled={props.disabled}
              error={props.errors?.duration_hours}
              onChange={props.form.setDurationHours}
              onEdited={props.onChange}
            />
            <NumberField
              name="duration_minutes"
              label={t('recurring.rules.editor.durationMinutes')}
              value={props.form.durationMinutes()}
              max={59}
              disabled={props.disabled}
              error={props.errors?.duration_minutes}
              onChange={props.form.setDurationMinutes}
              onEdited={props.onChange}
            />
          </div>
        </Show>
      </div>

      <div class="recurrence-rule-fields">
        <SelectField
          name="end_mode"
          label={t('recurring.rules.editor.endMode')}
          value={props.form.endMode()}
          disabled={props.disabled}
          error={props.errors?.end_mode}
          options={[
            { label: t('recurring.rules.editor.never'), value: 'never' },
            { label: t('recurring.rules.editor.untilDate'), value: 'date' },
            { label: t('recurring.rules.editor.afterCount'), value: 'count' },
          ]}
          onChange={(value) => {
            props.form.setEndMode(value)
            props.onChange()
          }}
        />
        <Show when={props.form.endMode() === 'date'}>
          <DateTimePicker
            mode="date"
            name="repeat_until"
            label={t('recurring.rules.editor.repeatUntil')}
            value={props.form.repeatUntil()}
            required
            disabled={props.disabled}
            error={props.errors?.repeat_until}
            onChange={(value) => {
              props.form.setRepeatUntil(value)
              props.onChange()
            }}
            onValidityChange={props.form.setRepeatUntilValid}
          />
        </Show>
        <Show when={props.form.endMode() === 'count'}>
          <NumberField
            name="occurrences_limit"
            label={t('recurring.rules.editor.occurrencesLimit')}
            value={props.form.occurrencesLimit()}
            disabled={props.disabled}
            error={props.errors?.occurrences_limit}
            onChange={props.form.setOccurrencesLimit}
            onEdited={props.onChange}
          />
        </Show>
      </div>
    </>
  )
}

function MonthlyRuleFields(props: {
  disabled: boolean
  errors?: Readonly<Record<string, string>>
  form: RecurrenceRuleForm
  onChange: () => void
}) {
  const { t } = useI18n()
  const setMode = (value: MonthRuleMode) => {
    props.form.setMonthRuleMode(value)
    props.onChange()
  }
  return (
    <div class="recurrence-month-rule">
      <div class="recurrence-rule-fields">
        <SelectField
          name="month_rule_mode"
          label={t('recurring.rules.editor.monthRule')}
          value={props.form.monthRuleMode()}
          disabled={props.disabled}
          error={props.errors?.month_rule_mode}
          options={[
            {
              label: t('recurring.rules.editor.monthDay'),
              value: 'month_day',
            },
            {
              label: t('recurring.rules.editor.ordinalWeekday'),
              value: 'ordinal_weekday',
            },
          ]}
          onChange={setMode}
        />
        <Show
          when={props.form.monthRuleMode() === 'month_day'}
          fallback={
            <>
              <SelectField
                name="ordinal_week"
                label={t('recurring.rules.editor.ordinalWeek')}
                value={props.form.ordinalWeek()}
                disabled={props.disabled}
                error={props.errors?.ordinal_week}
                options={['1', '2', '3', '4', '5', '-1'].map((value) => ({
                  label: t(
                    `recurring.rules.editor.ordinalWeekOption.${value === '-1' ? 'last' : `week${value}`}` as TranslationKey,
                  ),
                  value,
                }))}
                onChange={(value) => {
                  props.form.setOrdinalWeek(value)
                  props.onChange()
                }}
              />
              <SelectField
                name="ordinal_weekday"
                label={t('recurring.rules.editor.ordinalWeekdayName')}
                value={String(props.form.ordinalWeekday())}
                disabled={props.disabled}
                error={props.errors?.ordinal_weekday}
                options={weekdays.map((value) => ({
                  label: t(weekdayLabelKeys[value]),
                  value: String(value),
                }))}
                onChange={(value) => {
                  props.form.setOrdinalWeekday(Number(value) as Weekday)
                  props.onChange()
                }}
              />
            </>
          }
        >
          <NumberField
            name="month_day"
            label={t('recurring.rules.editor.monthDayNumber')}
            value={props.form.monthDay()}
            disabled={props.disabled}
            error={props.errors?.month_day}
            onChange={props.form.setMonthDay}
            onEdited={props.onChange}
          />
        </Show>
      </div>
      <SelectField
        name="business_day_policy"
        label={t('recurring.rules.editor.businessDay.label')}
        value={props.form.businessDayPolicy()}
        disabled={props.disabled}
        error={props.errors?.business_day_policy}
        options={businessDayPolicies.map((value) => ({
          label: t(businessDayPolicyLabelKeys[value]),
          value,
        }))}
        onChange={(value) => {
          props.form.setBusinessDayPolicy(value)
          props.onChange()
        }}
      />
    </div>
  )
}

function NumberField(props: {
  disabled: boolean
  error?: string
  label: string
  max?: number
  name: string
  onChange: (value: string) => void
  onEdited: () => void
  value: string
}) {
  const errorId = () => `recurrence-${props.name.replaceAll('_', '-')}-error`
  return (
    <label class="recurrence-rule-number-field">
      <span>{props.label}</span>
      <input
        name={props.name}
        type="text"
        inputmode="numeric"
        pattern="[0-9]*"
        value={props.value}
        disabled={props.disabled}
        aria-invalid={props.error === undefined ? undefined : 'true'}
        aria-describedby={props.error === undefined ? undefined : errorId()}
        onInput={(event) => {
          const digits = event.currentTarget.value.replace(/\D/g, '')
          const normalizedValue =
            props.max !== undefined && Number(digits) > props.max
              ? String(props.max)
              : digits
          event.currentTarget.value = normalizedValue
          props.onChange(normalizedValue)
          props.onEdited()
        }}
      />
      <Show when={props.error}>
        {(error) => (
          <small id={errorId()} class="recurrence-rule-field-error">
            {error()}
          </small>
        )}
      </Show>
    </label>
  )
}
