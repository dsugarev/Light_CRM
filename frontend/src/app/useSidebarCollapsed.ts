import { useState } from 'react'

const KEY = 'crm.sidebar.collapsed'

function read(): boolean {
  try {
    return sessionStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

/** UX-02: the sidebar's collapsed state is remembered for the browser session. */
export function useSidebarCollapsed(): [boolean, (collapsed: boolean) => void] {
  const [collapsed, setCollapsed] = useState(read)
  const update = (value: boolean) => {
    setCollapsed(value)
    try {
      if (value) sessionStorage.setItem(KEY, '1')
      else sessionStorage.removeItem(KEY)
    } catch {
      // Storage blocked: the choice lasts until the page reloads.
    }
  }
  return [collapsed, update]
}
