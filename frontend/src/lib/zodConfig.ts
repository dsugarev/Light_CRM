import { z } from 'zod'

// The CSP forbids eval (script-src 'self'). Zod 4 probes `new Function` to decide
// whether to compile validators; the blocked probe is reported as a CSP violation
// (Firefox). Jitless validation skips the probe; it is fast enough for our forms.
z.config({ jitless: true })
