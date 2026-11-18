# Integration guide: Conclusion, ERP and Billing

For the teams that connect Conclusion, ERP and Billing to the CRM. It explains how to get access, call the API, keep a copy of CRM data in sync, write your own IDs back, and receive webhooks. The full contract is the OpenAPI document; the rules behind it are in [`05-api-specification.md`](05-api-specification.md) (section 19 for integrations).

| You need | Where |
|---|---|
| Every endpoint, field and error code | OpenAPI: `GET https://<crm-host>/api/v1/openapi.json` (needs your API key), or the snapshot [`api/openapi.json`](api/openapi.json) |
| The scope each operation needs | `x-required-scope` on each operation in the OpenAPI document; table in API spec 19.3 |
| Ready-made requests | Postman collection [`integration/light-crm.postman_collection.json`](integration/light-crm.postman_collection.json) (import it, set the variables `baseUrl`, `apiKey`, `system`) |
| A working webhook receiver | [`deploy/examples/webhook_receiver.py`](../deploy/examples/webhook_receiver.py) (Python, standard library only) |

## 1. Getting access

1. Your system is registered in the CRM as an **integration client** (for example "ERP"). The CRM Admin sets its **scopes** (what it may read or write), an optional **IP allowlist** and a **default owner** for records you create.
2. The Admin issues an **API key** and gives it to your technical contact through a secure channel. The key looks like `crm_prod_3f9c1a2b7d4e5f60_<43 characters>`. It is shown **once**; the CRM stores only a hash, so a lost key cannot be recovered, only replaced.
3. Keys expire (12 months by default, 24 at most). To rotate without downtime, ask for a second key, switch over, then ask for the old one to be revoked. A client can have two active keys.
4. New clients start **inactive** and are switched on once the data flow is agreed. Until then every call returns `401 auth.client_inactive`.

Initial profiles (API spec 19.9) are read-only, plus writing back your own system's IDs. Write scopes are granted only after the data flow is confirmed.

## 2. Calling the API

```
GET /api/v1/me HTTP/1.1
Host: crm.example.bg
Authorization: Bearer crm_prod_3f9c1a2b7d4e5f60_...
```

- HTTPS only, JSON in UTF-8 (Cyrillic included), `snake_case` fields, timestamps in UTC ISO 8601 (`2026-11-17T09:30:00Z`), money as decimal strings (`"125000.00"`) with a `currency` field.
- Send the key only in the `Authorization` header, never in a URL. Do not send cookies: a request with both is refused (`400 auth.mixed_credentials`).
- `GET /api/v1/me` is the connection test: it returns `principal_type: "integration"`, your `system` and your `scopes`.
- Ignore response fields you do not know: new fields can appear in any release (section 9).

### Errors

Errors are RFC 9457 problem details. Use `code`, never the text:

```json
{ "type": "https://crm.internal/errors/permission.scope_missing", "status": 403,
  "code": "permission.scope_missing", "required_scope": "leads:read", "request_id": "0b9c..." }
```

| Status | Code | What to do |
|---|---|---|
| 401 | `auth.api_key_invalid` | Key wrong, revoked or expired: get a new key |
| 401 | `auth.client_inactive` | The client is switched off: contact the CRM Admin |
| 403 | `auth.ip_not_allowed` | Call from an address on your allowlist |
| 403 | `permission.scope_missing` | Your client lacks `required_scope` |
| 403 | `permission.not_for_integrations` | The endpoint is for people only (admin, import, export, audit, assistant) |
| 404 | `resource.not_found` | No such record (or path) |
| 409 | `conflict.version_mismatch` | The record changed since you read it: read again, then retry |
| 409 | `external_reference.conflict` | That external ID is already linked to another record |
| 422 | `validation.failed` | See `errors[]`: `{ "field", "code" }` per field |
| 422 | `owner.required` | Give `owner_id`, or ask the Admin to set a default owner |
| 429 | `rate_limit.exceeded` | Wait `Retry-After` seconds |
| 5xx | `server.internal_error` | Retry later with backoff; quote `request_id` when reporting |

Every response carries `X-Request-ID`; quote it when you report a problem.

### Rate limit

Each client has its own limit, 300 requests per minute unless agreed otherwise. Above it you get `429` with `Retry-After`. Sync with large pages (below) rather than many small calls.

## 3. Keeping a copy in sync (sync mode)

Lists of organizations, contacts, leads, opportunities and activities have a **sync mode**: pass `updated_since` and follow `next_cursor`.

```
GET /api/v1/organizations?updated_since=2026-11-17T00:00:00Z&page_size=500
→ { "items": [ ... ], "next_cursor": "eyJ1Ijoi..." }
GET /api/v1/organizations?updated_since=2026-11-17T00:00:00Z&page_size=500&cursor=eyJ1Ijoi...
→ { "items": [ ... ], "next_cursor": null }
```

- Items come in `(updated_at, id)` order. Keep calling with `cursor` until `next_cursor` is `null`, then store the largest `updated_at` you saw and use it as `updated_since` next time.
- Archived and anonymized records are included, so you can mirror removals (`archived_at` is set).
- A record changed while you page can appear twice; keep the newest `updated_at` per `id`.
- Changes from the last few seconds come on your next run, so nothing committed is skipped.

Run a sync at least nightly even when you use webhooks: webhooks give timeliness, sync is the safety net.

## 4. Your IDs in the CRM (external references)

Store your own identifier on the CRM record instead of keeping a mapping table on your side. One ID per record per system; an ID is unique per system and record type.

```
PUT /api/v1/organizations/{id}/external-references/erp
{ "external_id": "C-10023", "url": "https://erp.example.bg/customers/C-10023" }
→ 200 { "entity_type": "organization", "entity_id": "...", "external_id": "C-10023", ... }

GET /api/v1/external-references?system=erp&external_id=C-10023
→ 200 { "entity_type": "organization", "entity_id": "...", ... }        (or 404)

GET /api/v1/opportunities?stage_type=won&external_system=erp&has_external_reference=false
→ won deals your system has not picked up yet
```

- You can write only your own system's IDs (`erp` for the ERP client); others return `403 external_reference.system_mismatch`. This needs the `external-references:write` scope. Reading needs only the record type's read scope.
- `url` is optional, must be HTTPS, and is shown to CRM users as a link to your system.
- `DELETE` on the same path removes the ID.
- The filters `external_system`, `external_id` and `has_external_reference` work on the organization, contact, lead and opportunity lists.

## 5. Creating records safely (idempotency)

If your system has write scopes, send an `Idempotency-Key` header on every `POST` (a UUID, or your own record ID; 1–255 characters):

```
POST /api/v1/organizations
Idempotency-Key: erp-customer-C-10023
{ "name": "Акме ЕООД", "owner_id": "..." }
```

A retry with the same key and body within 24 hours returns the first response again with `Idempotent-Replayed: true`, so a timeout never creates a duplicate. The same key with a different body returns `422 idempotency.key_reused`; a retry while the first call is still running returns `409 idempotency.in_progress` (wait and retry). Server errors (`5xx`) are not stored, so the retry runs again.

Records you create need a human owner: send `owner_id` (find people with `GET /api/v1/users/lookup?email=`), or rely on the client's default owner.

## 6. Webhooks

The CRM can push changes to your HTTPS endpoint. The Admin creates a **subscription**: your URL (HTTPS, on a host the CRM allows), the event types, and a **signing secret** shown once.

### Events

`organization.created`, `.updated`, `.archived`; `contact.created`, `.updated`, `.archived`, `.anonymized`; `lead.created`, `.updated`, `.status_changed`, `.converted`; `opportunity.created`, `.updated`, `.stage_changed`, `.closed_won`, `.closed_lost`, `.reopened`; `external_reference.updated`; and `ping` (test). A subscription may use `opportunity.*` or `*`. You receive only events for record types your scopes let you read.

### Request

```
POST /hooks/crm HTTP/1.1
Content-Type: application/json
User-Agent: LightCRM-Webhooks/1
X-CRM-Event-Id: evt_0193f1c2...
X-CRM-Event-Type: opportunity.closed_won
X-CRM-Delivery-Attempt: 1
X-CRM-Signature: t=1763380000,v1=5f2b...e9
```

```json
{
  "id": "evt_0193f1c2...",
  "type": "opportunity.closed_won",
  "api_version": "v1",
  "occurred_at": "2026-11-17T14:03:12Z",
  "actor": { "type": "user", "id": "...", "name": "Ivan Petrov" },
  "data": {
    "entity_type": "opportunity",
    "entity_id": "0193...",
    "version": 9,
    "changes": ["actual_close_date", "probability", "stage_id"],
    "object": { "...": "the record as GET /api/v1/opportunities/{id} returns it" }
  }
}
```

- `object` is the record **as it is when the event is delivered**, so a retried or late event carries current data. It is `null` if the record no longer exists, and for `ping`.
- `version` is the record's version for leads and opportunities (`null` for organizations and contacts; use `occurred_at`). Ignore events older than what you already have.
- `actor.type` is `user`, `integration` (with `client_id`) or `system`. Events caused by your own API calls are delivered to you too; skip them by `actor.client_id`.
- For `external_reference.updated`, `data.system` names the system and `object` is the reference (or `null` when it was removed).

### What your endpoint must do

1. **Verify the signature** before anything else (below). Reject with `401` if it does not match.
2. **Reject old timestamps** (more than 5 minutes) to stop replays.
3. **Deduplicate on `id`**: delivery is at least once, and an Admin can redeliver.
4. **Answer `2xx` within 10 seconds**, then do the work. Redirects are not followed and count as failures.

Failed deliveries are retried with backoff (about 1 minute, 5 minutes, 30 minutes, 2 hours, 6 hours, then every 6 hours) for 72 hours, then marked failed. Events for the same record are delivered in order: a later one waits while an earlier one is being retried. A subscription that fails continuously for 72 hours is suspended and the CRM Admins are alerted; after you fix the endpoint, they resume it. Events raised while your endpoint is down are delivered afterwards.

### Verifying the signature

`v1` is the hex HMAC-SHA256 of `"<t>.<raw body>"` with the subscription's secret. For 24 hours after the Admin rotates the secret, the header carries two signatures (`t=...,v1=<old>,v1=<new>`); accept either. Compute over the **raw bytes** you received, before parsing JSON.

**Python** (tested in the CRM's test suite against the CRM's own signer):

```python verify
import hashlib
import hmac
import time


def verify_signature(secret: str, header: str, body: bytes, tolerance: int = 300) -> bool:
    timestamp, signatures = None, []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t" and value.isdigit():
            timestamp = int(value)
        elif key == "v1":
            signatures.append(value)
    if timestamp is None or abs(time.time() - timestamp) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in signatures)
```

**C#** (.NET 6 or later; provided as a starting point, not tested by the CRM team):

```csharp
using System.Security.Cryptography;
using System.Text;

static bool VerifySignature(string secret, string header, byte[] body, int toleranceSeconds = 300)
{
    long? timestamp = null;
    var signatures = new List<string>();
    foreach (var part in header.Split(','))
    {
        var kv = part.Trim().Split('=', 2);
        if (kv.Length != 2) continue;
        if (kv[0] == "t" && long.TryParse(kv[1], out var t)) timestamp = t;
        else if (kv[0] == "v1") signatures.Add(kv[1]);
    }
    if (timestamp is null) return false;
    if (Math.Abs(DateTimeOffset.UtcNow.ToUnixTimeSeconds() - timestamp.Value) > toleranceSeconds) return false;

    var prefix = Encoding.UTF8.GetBytes($"{timestamp}.");
    var message = new byte[prefix.Length + body.Length];
    prefix.CopyTo(message, 0);
    body.CopyTo(message, prefix.Length);
    using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
    var expected = Encoding.ASCII.GetBytes(Convert.ToHexString(hmac.ComputeHash(message)).ToLowerInvariant());
    return signatures.Any(s => CryptographicOperations.FixedTimeEquals(expected, Encoding.ASCII.GetBytes(s)));
}
```

**Java** (11 or later; provided as a starting point, not tested by the CRM team):

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat; // Java 17; on 11 format the bytes yourself
import java.util.List;

static boolean verifySignature(String secret, String header, byte[] body, long toleranceSeconds) throws Exception {
    Long timestamp = null;
    List<String> signatures = new ArrayList<>();
    for (String part : header.split(",")) {
        String[] kv = part.trim().split("=", 2);
        if (kv.length != 2) continue;
        if (kv[0].equals("t") && kv[1].matches("\\d+")) timestamp = Long.parseLong(kv[1]);
        else if (kv[0].equals("v1")) signatures.add(kv[1]);
    }
    if (timestamp == null) return false;
    if (Math.abs(System.currentTimeMillis() / 1000 - timestamp) > toleranceSeconds) return false;

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
    mac.update((timestamp + ".").getBytes(StandardCharsets.UTF_8));
    byte[] expected = HexFormat.of().formatHex(mac.doFinal(body)).getBytes(StandardCharsets.US_ASCII);
    for (String s : signatures) {
        if (MessageDigest.isEqual(expected, s.getBytes(StandardCharsets.US_ASCII))) return true;
    }
    return false;
}
```

### Trying it out

Run the reference receiver, ask the CRM Admin to point a subscription at it, and press **Send test event**:

```bash
WEBHOOK_SECRET=whsec_... python3 deploy/examples/webhook_receiver.py --port 8443 \
    --tls-cert cert.pem --tls-key key.pem
```

It prints each verified event as one JSON line and answers `401` to anything with a bad signature. The Admin sees every attempt, with your status code and the first part of your response, in the CRM's delivery log.

## 7. A typical ERP flow

1. Receive `opportunity.closed_won` (subscription for that event).
2. Read the organization and its contacts: `GET /api/v1/organizations/{id}`, `GET /api/v1/organizations/{id}/contacts`.
3. Create the customer in ERP.
4. Write the customer number back: `PUT /api/v1/organizations/{id}/external-references/erp`.
5. Nightly: `GET /api/v1/opportunities?stage_type=won&external_system=erp&has_external_reference=false` and a sync-mode `GET /api/v1/organizations?updated_since=...` to catch anything missed.

## 8. Checklist before going live

- [ ] `GET /api/v1/me` returns your system and the scopes you expect.
- [ ] The key is stored in your secret store, not in code or logs; you know who asks for a new one.
- [ ] Sync stores the last `updated_at` and follows `next_cursor` to the end.
- [ ] Every `POST` sends an `Idempotency-Key`.
- [ ] Your webhook endpoint verifies signatures, rejects old timestamps, deduplicates on `id` and answers within 10 seconds.
- [ ] A **Send test event** from the CRM shows `2xx` in the delivery log.
- [ ] You handle `429` (`Retry-After`) and `409 conflict.version_mismatch`.

## 9. Versioning and changes

You build against `/api/v1`. It changes only additively: new endpoints, new optional request fields, new response fields, new event types and new values in reference lists can appear in any release, so ignore what you do not know. A breaking change goes to `/api/v2`; `v1` then stays available for at least 6 months, announced with `Deprecation` and `Sunset` response headers and in the release notes, which list API changes in their own section.
