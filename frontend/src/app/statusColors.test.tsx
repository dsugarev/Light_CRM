import { render, screen } from '@testing-library/react'

import { ImportStatusBadge } from '@/features/imports/ImportStatusBadge'
import { LeadStatusBadge } from '@/features/leads/LeadStatusBadge'
import { StageBadge, StaleBadge } from '@/features/opportunities/StageBadge'
import { contrast, over, token, WHITE } from '@/test/themeContrast'

// UX-01 / NFR-10, loop 2: status colors come from theme tokens and keep text contrast.

describe('NFR-10 status color contrast (loop 2)', () => {
  it.each(['success', 'warning', 'info', 'destructive'])(
    'NFR-10 %s text keeps 4.5:1 on white and on its 10% badge tint',
    (name) => {
      const color = token(name)
      expect(contrast(color, WHITE)).toBeGreaterThanOrEqual(4.5)
      expect(contrast(color, over(color, 0.1, WHITE))).toBeGreaterThanOrEqual(4.5)
    },
  )

  it('NFR-10 the contrast helper agrees with a known pair (black on white is 21:1)', () => {
    expect(contrast([0, 0, 0], WHITE)).toBeCloseTo(21, 5)
  })
})

function variantOf(text: string): string {
  const cls = screen.getByText(text).className
  return /\btext-(success|warning|info|destructive)\b/.exec(cls)?.[1] ?? 'neutral'
}

describe('UX-01 status badges use semantic colors (loop 2)', () => {
  it('FR-LEAD-05 lead statuses: new blue, qualified green, disqualified red, others neutral', () => {
    render(
      <>
        <LeadStatusBadge status="new" />
        <LeadStatusBadge status="contacted" />
        <LeadStatusBadge status="qualified" />
        <LeadStatusBadge status="converted" />
        <LeadStatusBadge status="disqualified" />
      </>,
    )
    expect(variantOf('New')).toBe('info')
    expect(variantOf('Contacted')).toBe('neutral')
    expect(variantOf('Qualified')).toBe('success')
    expect(variantOf('Converted')).toBe('neutral')
    expect(variantOf('Disqualified')).toBe('destructive')
  })

  it('FR-OPP-06 stages: open blue, won green, lost red; stale amber', () => {
    const stage = (stage_type: 'open' | 'won' | 'lost', name: string) => ({
      id: name,
      name_en: name,
      name_bg: name,
      stage_type,
      position: 1,
      default_probability: 0,
    })
    render(
      <>
        <StageBadge stage={stage('open', 'Proposal')} />
        <StageBadge stage={stage('won', 'Won')} />
        <StageBadge stage={stage('lost', 'Lost')} />
        <StaleBadge />
      </>,
    )
    expect(variantOf('Proposal')).toBe('info')
    expect(variantOf('Won')).toBe('success')
    expect(variantOf('Lost')).toBe('destructive')
    expect(variantOf('Needs attention')).toBe('warning')
  })

  it('FR-IMP-01 imports: steps in progress blue, imported green, rolled back neutral', () => {
    render(
      <>
        <ImportStatusBadge status="validated" />
        <ImportStatusBadge status="committed" />
        <ImportStatusBadge status="rolled_back" />
      </>,
    )
    expect(variantOf('Checked')).toBe('info')
    expect(variantOf('Imported')).toBe('success')
    expect(variantOf('Rolled back')).toBe('neutral')
  })
})
