import { useRef } from 'react'

import { Input } from '@/components/ui/input'

/** Search box that reports its value after typing pauses (300 ms). Uncontrolled:
 * remount it with a new `key` to reset it from outside. */
export function SearchInput({
  value,
  onChange,
  label,
}: {
  value: string
  onChange: (value: string) => void
  label: string
}) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  return (
    <Input
      type="search"
      aria-label={label}
      placeholder={label}
      defaultValue={value}
      onChange={(e) => {
        const next = e.target.value.trim()
        clearTimeout(timer.current)
        timer.current = setTimeout(() => {
          if (next !== value) onChange(next)
        }, 300)
      }}
    />
  )
}
