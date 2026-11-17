# ADR 0010: External references table for cross-system IDs

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
ERP customer numbers, Billing account IDs and Conclusion IDs must be stored, and more systems may follow.

## Decision
A single `external_reference` table (entity_type, entity_id, external_system_id, external_id, url) with uniqueness per system and record type. Never add columns such as `erp_customer_number` to business tables. Systems are a lookup list (`external_system`). Built in Phase 6.

## Consequences
New integrated systems need configuration only. Lookups by external ID go through one indexed table.
