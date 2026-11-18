import { z } from 'zod'

import './zodConfig'

it('ASVS 5.2.4 Zod never probes eval, which the CSP forbids', () => {
  expect(z.config().jitless).toBe(true)
})
