import { useEffect, useRef } from 'react'

import { Input } from '@/components/ui/input'

/** Search box that reports its value after typing pauses (300 ms). Uncontrolled while
 * typing; when `value` changes from outside (for example "Clear filters"), the box follows. */
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
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (input.current && input.current.value.trim() !== value) {
      clearTimeout(timer.current)
      input.current.value = value
    }
  }, [value])
  return (
    <Input
      ref={input}
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
