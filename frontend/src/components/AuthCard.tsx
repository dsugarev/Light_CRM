import type { ReactNode } from 'react'

/** UX-03: the header and frame of the signed-out pages (sign in, set and reset password). */
export function AuthCard({
  title,
  description,
  children,
}: {
  title: string
  description?: string | undefined
  children: ReactNode
}) {
  return (
    <section className="mx-auto mt-16 w-full max-w-sm rounded-xl border bg-card p-6 shadow-sm">
      <header className="mb-6 flex flex-col gap-2">
        <h1 className="text-xl font-semibold">{title}</h1>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </header>
      {children}
    </section>
  )
}
