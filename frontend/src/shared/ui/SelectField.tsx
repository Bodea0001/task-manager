import { Select } from '@kobalte/core/select'
import Check from 'lucide-solid/icons/check'
import ChevronDown from 'lucide-solid/icons/chevron-down'
import { Show } from 'solid-js'

import './select-field.css'

export interface SelectOption<Value extends string = string> {
  label: string
  value: Value
}

export function SelectField<Value extends string>(props: {
  compact?: boolean
  disabled?: boolean
  error?: string
  label: string
  name?: string
  onChange: (value: Value) => void
  options: SelectOption<Value>[]
  portalMount?: HTMLElement
  value: Value
}) {
  const errorId = () =>
    props.name === undefined
      ? undefined
      : `select-${props.name.replaceAll('_', '-')}-error`
  const selectedOption = () =>
    props.options.find((option) => option.value === props.value)

  return (
    <Select<SelectOption<Value>>
      class={`select-field${props.compact ? ' select-field--compact' : ''}`}
      name={props.name}
      options={props.options}
      optionValue="value"
      optionTextValue="label"
      value={selectedOption()}
      disabled={props.disabled}
      disallowEmptySelection
      onChange={(option) => {
        if (option !== null) {
          props.onChange(option.value)
        }
      }}
      itemComponent={(itemProps) => (
        <Select.Item class="select-field-item" item={itemProps.item}>
          <Select.ItemLabel>{itemProps.item.rawValue.label}</Select.ItemLabel>
          <Select.ItemIndicator class="select-field-indicator">
            <Check size={15} strokeWidth={2.2} />
          </Select.ItemIndicator>
        </Select.Item>
      )}
    >
      <Select.Label
        class={props.compact ? 'visually-hidden' : 'select-field-label'}
      >
        {props.label}
      </Select.Label>
      <Select.HiddenSelect />
      <Select.Trigger
        class="select-field-trigger"
        aria-invalid={props.error === undefined ? undefined : 'true'}
        aria-describedby={props.error === undefined ? undefined : errorId()}
      >
        <Select.Value<SelectOption<Value>>>
          {(state) => state.selectedOption().label}
        </Select.Value>
        <Select.Icon class="select-field-icon">
          <ChevronDown size={16} strokeWidth={1.9} />
        </Select.Icon>
      </Select.Trigger>
      <Show when={props.error}>
        {(error) => (
          <small id={errorId()} class="select-field-error">
            {error()}
          </small>
        )}
      </Show>
      <Select.Portal mount={props.portalMount}>
        <Select.Content class="select-field-content">
          <Select.Listbox class="select-field-listbox" />
        </Select.Content>
      </Select.Portal>
    </Select>
  )
}
