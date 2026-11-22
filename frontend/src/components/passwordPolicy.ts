/** The password policy the backend enforces (identity/passwords.py, FR-AUTH-03). */
export const PASSWORD_MIN_LENGTH = 12
export const PASSWORD_MAX_LENGTH = 128

export type Strength = 0 | 1 | 2 | 3 | 4

/**
 * ASVS 2.1.8: a strength guide while typing (0 = empty, 1 weak … 4 strong). Length counts
 * most (NIST 800-63B), then the mix of letter cases, digits and symbols; one repeated
 * character stays weak. A guide only: the policy is the rules above, and common passwords
 * are refused by the server.
 */
export function passwordStrength(password: string): Strength {
  if (password === '') return 0
  if (password.length < PASSWORD_MIN_LENGTH || /^(.)\1*$/u.test(password)) return 1
  const kinds = [/\p{Ll}/u, /\p{Lu}/u, /\p{N}/u, /[^\p{L}\p{N}]/u].filter((kind) =>
    kind.test(password),
  ).length
  let score = 1
  if (password.length >= 16) score += 1
  if (password.length >= 20) score += 1
  if (kinds >= 3) score += 1
  return Math.min(score, 4) as Strength
}
