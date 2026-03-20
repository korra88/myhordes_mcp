# Authentication & Rate Limiting

Source: `src/EventSubscriber/APIRequestListener.php`

## Authentication Model

The external API uses a two-key system (not OAuth, not JWT):

1. **User Key** (`userkey`): The user's `externalId` field — a 32-char hex string. Each MyHordes user has one. This identifies *whose data* to return.

2. **App Key** (`appkey`): The `secret` field of a registered `ExternalApp` entity. This identifies *which application* is making the request.

Both are passed as query parameters or POST body fields.

### Key Lookup

```
userkey → User.externalId   (ExternalAccessTokens are NOT used for API v1)
appkey  → ExternalApp.secret
```

### Debug/Test Mode ("fefe")

When both `userkey` and `appkey` are set to `fefe0000fefe0000fefe0000fefe0000`, and the endpoint has `fefe: true` in its `@ExternalAPI` annotation, the API uses the currently logged-in session user instead of doing a key lookup. This is only useful for browser-based testing while logged in.

The `townlist` and `towns` endpoints explicitly set `fefe: false` — no debug mode.

## Rate Limiting

Four rate limit buckets based on key combination:

| Keys Present | Limiter | Scoped By |
|---|---|---|
| None | `publicApi` | Global (`pbk`) |
| User only | `anonymousApi` | User ID |
| App only | `authenticatedApi` | App ID |
| Both | `authenticatedApi` + `authenticatedPersonalApi` | App ID + `userId.appId` |

Rate limit costs are defined per-endpoint via the `cost` parameter in the `@ExternalAPI` annotation (default: 1).

### Response Headers

Every API response includes:
```
X-RateLimit-Limit: <max tokens>
X-RateLimit-Remaining: <tokens left>
X-RateLimit-Retry-After: <unix timestamp>
```

When rate limited, the error response is:
```json
{"error": "rate_limit_reached"}
```

## Attack Lockout

During the nightly zombie attack (`TimeKeeperService::isDuringAttack()` returns true), **all external API calls are rejected** with:
```json
{"error": "nightly_attack"}
```

This is checked before authentication — even valid keys get rejected during attacks.

## Implications for MCP Server

1. **We need two keys**: `MYHORDES_API_KEY` (user key) and `MYHORDES_APP_KEY` (app key). Both are required for the `map` endpoint.

2. **Rate limiting is per-app**: We should cache responses where possible and batch our field requests into single `map` calls using SURLL.

3. **Attack window**: Our tools should handle the `nightly_attack` error gracefully and tell the user to wait.

4. **No interactive login**: Keys are static UUIDs — perfect for environment variable configuration.

## Entity Schema

### ExternalApp
```
id: int
name: string
owner: User (relation)
secret: string (32-char hex — the appkey)
url: string
contact: string
testing: bool
wiki: string
icon: Media (relation)
```

### ExternalAPIUsageRecord
```
id: int
api: ExternalAPIInterface (enum)
app: ExternalApp (nullable)
user: User (nullable)
timestamp: DateTime
debug: bool (fefe key was used)
```
