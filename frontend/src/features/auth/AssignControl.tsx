import { useState } from 'react'

import { NativeSelect } from '@/components/NativeSelect'
import { Button } from '@/components/ui/button'

import { useUserLookup } from './useUserLookup'

interface AssignControlProps {
  current: string
  pending: boolean
  label: string
  buttonLabel: string
  onAssign: (id: string) => void
}

/** Owner change for Managers+ (FR-LEAD-06): any active user can become the owner. */
export function AssignControl({
  current,
  pending,
  label,
  buttonLabel,
  onAssign,
}: AssignControlProps) {
  const users = useUserLookup(true)
  const [owner, setOwner] = useState(current)
  return (
    <div className="flex items-center gap-2">
      <NativeSelect
        aria-label={label}
        value={owner}
        onChange={(e) => {
          setOwner(e.target.value)
        }}
        className="w-48"
      >
        {(users.data?.items ?? []).map((user) => (
          <option key={user.id} value={user.id}>
            {user.full_name}
          </option>
        ))}
      </NativeSelect>
      <Button
        type="button"
        variant="outline"
        disabled={pending || owner === current}
        onClick={() => {
          onAssign(owner)
        }}
      >
        {buttonLabel}
      </Button>
    </div>
  )
}
