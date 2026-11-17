export const HUMAN_ROLES = ['admin', 'sales_manager', 'sales_rep', 'viewer'] as const
export type HumanRole = (typeof HUMAN_ROLES)[number]
