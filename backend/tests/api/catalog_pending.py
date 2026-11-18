"""Catalog endpoints not built yet, keyed "METHOD path" -> spec section.

The route catalog test fails if an endpoint in docs/05-api-specification.md has
no route and is not listed here. Remove entries as each phase builds them.
"""

PENDING: dict[str, str] = {
    "POST /api/v1/auth/login/mfa": "3. Authentication and sessions",
    "POST /api/v1/auth/mfa/setup": "3. Authentication and sessions",
    "POST /api/v1/auth/mfa/confirm": "3. Authentication and sessions",
    "POST /api/v1/auth/mfa/disable": "3. Authentication and sessions",
    "GET /api/v1/contacts/{contact_id}/personal-data": "8. Contacts",
    "POST /api/v1/contacts/{contact_id}/anonymize": "8. Contacts",
    "GET /api/v1/assistant/status": "17. AI assistant",
    "GET /api/v1/assistant/conversations": "17. AI assistant",
    "POST /api/v1/assistant/conversations": "17. AI assistant",
    "GET /api/v1/assistant/conversations/{conversation_id}": "17. AI assistant",
    "PATCH /api/v1/assistant/conversations/{conversation_id}": "17. AI assistant",
    "DELETE /api/v1/assistant/conversations/{conversation_id}": "17. AI assistant",
    "POST /api/v1/assistant/conversations/{conversation_id}/messages": "17. AI assistant",
    "POST /api/v1/assistant/conversations/{conversation_id}/messages/{message_id}/stop": "17. AI assistant",
    "POST /api/v1/assistant/messages/{message_id}/save-as-note": "17. AI assistant",
    "GET /api/v1/integration-clients/{client_id}/webhook-subscriptions": "19. Integration API (Conclusion, ERP, Billing)",
    "POST /api/v1/integration-clients/{client_id}/webhook-subscriptions": "19. Integration API (Conclusion, ERP, Billing)",
    "PATCH /api/v1/webhook-subscriptions/{subscription_id}": "19. Integration API (Conclusion, ERP, Billing)",
    "DELETE /api/v1/webhook-subscriptions/{subscription_id}": "19. Integration API (Conclusion, ERP, Billing)",
    "POST /api/v1/webhook-subscriptions/{subscription_id}/rotate-secret": "19. Integration API (Conclusion, ERP, Billing)",
    "POST /api/v1/webhook-subscriptions/{subscription_id}/test": "19. Integration API (Conclusion, ERP, Billing)",
    "GET /api/v1/webhook-deliveries": "19. Integration API (Conclusion, ERP, Billing)",
    "GET /api/v1/webhook-deliveries/{delivery_id}": "19. Integration API (Conclusion, ERP, Billing)",
    "POST /api/v1/webhook-deliveries/{delivery_id}/redeliver": "19. Integration API (Conclusion, ERP, Billing)",
}
