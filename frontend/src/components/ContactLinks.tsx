import { websiteHref } from '@/lib/url'

/**
 * Contact details as links, so a click starts an email, a call or opens the site
 * (CRM best practice: one click to act on a record's details).
 */

export function EmailLink({ email }: { email: string | null | undefined }) {
  if (!email) return null
  return (
    <a className="hover:underline [overflow-wrap:anywhere]" href={`mailto:${email}`}>
      {email}
    </a>
  )
}

export function PhoneLink({ phone }: { phone: string | null | undefined }) {
  if (!phone) return null
  // tel: wants the digits and a leading +; spaces, dashes and brackets are for people.
  const dial = phone.replace(/[^\d+]/g, '')
  return (
    <a className="hover:underline" href={`tel:${dial}`}>
      {phone}
    </a>
  )
}

export function WebsiteLink({ website }: { website: string | null | undefined }) {
  if (!website) return null
  const href = websiteHref(website)
  if (!href) return <>{website}</>
  return (
    <a
      className="hover:underline [overflow-wrap:anywhere]"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {website}
    </a>
  )
}
