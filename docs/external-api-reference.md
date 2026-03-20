# MyHordes External API Reference

Reverse-engineered from `src/Controller/API/JSONv1Controller.php` and `src/EventSubscriber/APIRequestListener.php`.

This is the API our MCP server will call. The JSON v1 API is the most complete and the one we should target.

## Authentication

### Parameters (query string or POST body)
| Param | Required | Description |
|---|---|---|
| `userkey` | per-endpoint | User's External ID (UUID: `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`) |
| `appkey` | per-endpoint | Registered app secret (same format) |
| `lang` | optional | Language code: `de` (default), `en`, `fr`, `es`, or `all` |

### Auth Flow (APIRequestListener.php)
1. Extract `userkey`, `appkey`, `lang` from request
2. Reject if horde attack is in progress (`HordeAttacking` error)
3. Validate `userkey` → lookup `User.externalId` in database
4. Validate `appkey` → lookup `ExternalApp.secret` in database
5. Apply rate limiting based on key combination:
   - No keys → `publicApi` limiter
   - User key only → `anonymousApi` limiter (per user)
   - App key only → `authenticatedApi` limiter (per app)
   - Both keys → `authenticatedApi` + `authenticatedPersonalApi` (per app+user)
6. Record usage in `ExternalAPIUsageRecord`

### Rate Limit Response Headers
```
X-RateLimit-Limit: <max requests>
X-RateLimit-Remaining: <remaining>
X-RateLimit-Retry-After: <unix timestamp>
```

### Error Responses
```json
{"error": "invalid_userkey"}
{"error": "invalid_appkey"}
{"error": "nightly_attack"}
{"error": "rate_limit_reached"}
{"error": "server_error", "error_description": "UnknownAction(default)"}
```

---

## SURLL Field Selection Syntax

Most endpoints accept a `fields` parameter using the SURLL micro-language to select nested data.

**Syntax:** dot-prefixed field names, with parentheses for nesting.

```
# Simple fields
fields=id|name|avatar

# Nested objects
fields=city(.name|.water|.bank(.id|.count))

# This selects: { city: { name, water, bank: [{ id, count }] } }
```

The `languages` parameter uses the same syntax to select translation languages.

---

## Endpoints

### GET /api/x/json/status
**Auth:** none required
**Source:** `JSONv1Controller::api_json_status()` (line 105)

Returns server status.

```json
{
  "version": "3.2.1",
  "attack": false,
  "maintain": false
}
```

---

### GET /api/x/json/{type}
**Auth:** `userkey` + `appkey` required
**Source:** `JSONv1Controller::api_json()` (line 116)

Main dispatch endpoint. `{type}` determines what data is returned.

---

### type=me
**Source:** `getUserAPI("me")` → `getUserData()` (line 1557)

Returns the authenticated user's data.

**Default fields:** `id, name, avatar, isGhost, twinoidID`

**Available fields:**
| Field | Type | Description |
|---|---|---|
| `id` | int | User ID |
| `twinId` | int | Twinoid ID |
| `etwinId` | string | Eternaltwin ID |
| `name` | string | Username |
| `locale` | string | User's language |
| `avatar` | string/null | Avatar URL |
| `avatarData` | object/null | `{url, x, y, classic, format}` |
| `isGhost` | bool | Not in any active town |
| `dead` | bool | Dead in current town |
| `out` | bool | Currently outside town |
| `ban` | bool | Banished |
| `hero` | bool | Heroic profession |
| `baseDef` | int | Home base defense |
| `homeMessage` | string | Home description |
| `x`, `y` | int | Map position |
| `mapId` | int | Current town ID |
| `job` | object | `{uid, name}` — current profession |
| `map` | object | Current town map data (nested) |
| `playedMaps` | array | Past life history |
| `rewards` | array | Picto/achievement collection |
| `contacts` | array | Friends list (only for `me`) |

---

### type=user
**Source:** `getUserAPI("user")` (line 327)

**Extra param:** `id` (user ID)

Returns another user's public data. Same fields as `me` minus `contacts` and `twinoidID`.

---

### type=users
**Source:** `getUsersAPI()` (line 306)

**Extra param:** `ids` (comma-separated user IDs)

Returns array of user data for multiple users.

---

### type=map
**Auth:** `userkey` + `appkey`
**Source:** `getMapAPI()` → `getMapData()` (line 1231)

**Extra param:** `mapId` (town ID, required)

Returns comprehensive town + map data. **This is the most important endpoint for our MCP server.**

**Default fields:** `date, days, season, id, hei, wid, bonusPts, conspiracy, custom, city`

**Top-level fields:**
| Field | Type | Description |
|---|---|---|
| `id` | int | Town ID |
| `date` | string | Current datetime |
| `wid` | int | Map width |
| `hei` | int | Map height |
| `days` | int | Current game day |
| `season` | int | Season number |
| `phase` | string | `alpha`, `import`, `beta`, `native` |
| `source` | string | Origin server domain |
| `bonusPts` | int | Bonus score points |
| `conspiracy` | bool | Insurrection progress >= 100% |
| `guide` | int/null | Guide citizen's user ID |
| `shaman` | int/null | Shaman citizen's user ID |
| `cata` | int/null | Catapult operator's user ID |
| `custom` | bool | Custom game rules |
| `language` | string | Town language |
| `city` | object | Town details (see below) |
| `citizens` | array | Living citizen list |
| `cadavers` | array | Dead citizen list |
| `expeditions` | array | Expedition routes |
| `zones` | array | Map tiles |

---

### type=map → city (nested)
**Source:** `getCityData()` (line 736)

**Default fields:** `name, water, x, y, door, chaos, hard, devast`

| Field | Type | Description |
|---|---|---|
| `name` | string | Town name |
| `water` | int | Well water remaining |
| `x`, `y` | int | Town center coordinates |
| `door` | bool | Gate open (true) or closed |
| `chaos` | bool | Town in chaos mode |
| `hard` | bool | Panda (hardcore) mode |
| `type` | string | Town class name |
| `devast` | bool | Town is devastated |
| `bank` | array | Bank inventory items |
| `buildings` | array | Completed buildings |
| `chantiers` | array | Construction sites (incomplete) |
| `news` | object | Today's gazette/newspaper |
| `defense` | object | Full defense breakdown |
| `upgrades` | object | Building upgrade list |
| `estimations` | object | Tonight's attack estimation |
| `estimationsNext` | object | Tomorrow's attack estimation |

---

### type=map → city → bank (nested)
**Source:** `getBankData()` (line 476)

**Default fields:** `id, count, broken`

Returns array of items in the town bank:
```json
[
  {"id": 42, "count": 5, "broken": false},
  {"id": 17, "count": 12, "broken": false}
]
```

Items with `hidden=true` are excluded. Duplicates (same prototype + broken state) are aggregated.

---

### type=map → city → defense (nested)
**Source:** `getDefenseData()` (line 905)

**Default fields:** `total, base, buildings, upgrades, items, itemsMul, citizenHomes, citizenGuardians, watchmen, souls, temp, cadavers, guardiansInfos, bonus`

| Field | Type | Description |
|---|---|---|
| `total` | int | Total defense (all sources, scaled) |
| `base` | int | Base defense (default 10) |
| `buildings` | int | Defense from building base values |
| `upgrades` | int | Defense from building upgrade votes |
| `items` | int | Count of defense items in bank |
| `itemsMul` | float | Defense item multiplier (Defensive Focus building) |
| `citizenHomes` | int | Defense from citizen houses |
| `citizenGuardians` | int | Defense from guardians |
| `watchmen` | float | Nightwatch defense contribution |
| `souls` | int | Soul defense (if > 0) |
| `temp` | int | Temporary defense bonuses |
| `cadavers` | int | Cemetery defense (if > 0) |
| `bonus` | float | Overall scale modifier (if > 1) |
| `guardiansInfos` | object | `{gardians: count, def: bonus_per}` |

---

### type=map → city → estimations / estimationsNext (nested)
**Source:** `getEstimationData()` (line 1032)

**Default fields:** `days, min, max, maxed`

| Field | Type | Description |
|---|---|---|
| `days` | int | Game day |
| `min` | int | Minimum estimated zombie attack |
| `max` | int | Maximum estimated zombie attack |
| `maxed` | bool | Estimation is at 100% accuracy |

---

### type=map → city → news (nested)
**Source:** `getNewsData()` (line 1372)

**Default fields:** `z, def, content`

| Field | Type | Description |
|---|---|---|
| `z` | int | Last night's zombie attack count |
| `def` | int | Defense value at attack time |
| `content` | string/object | Gazette text (string if 1 lang, object if multi) |
| `regenDir` | string | Wind/regeneration direction (requires Search Tower) |
| `water` | int | Water lost last night |

---

### type=map → city → buildings / chantiers (nested)
**Source:** `getChantiersData()` (line 545)

- `buildings` = completed structures
- `chantiers` = construction sites (incomplete)

**Default fields:** `id, icon, name, desc, pa, breakable, def, temporary`

| Field | Type | Description |
|---|---|---|
| `id` | int | BuildingPrototype ID |
| `icon` | string | Icon asset path |
| `name` | string | Translated name |
| `desc` | string | Translated description |
| `pa` | int | Base AP cost |
| `paCurrent` | int | Adjusted AP (with rarity) |
| `life` | int | Current HP |
| `maxLife` | int | Maximum HP |
| `votes` | int | Construction vote count |
| `breakable` | bool | Can be destroyed |
| `def` | int | Defense contribution |
| `hasUpgrade` | bool | Has upgrade text |
| `rarity` | int | Base blueprint rarity |
| `rarityCurrent` | int | Current rarity in town |
| `difficulty` | int | Difficulty level |
| `order` | int | Sort order |
| `temporary` | bool | Temporary building |
| `parent` | int | Parent building ID (upgrade chain) |
| `resources` | array | Required resources (prototype) |
| `resourcesCurrent` | array | Adjusted resources (current) |
| `actions` | int | AP invested so far |
| `hasLevels` | int | Current upgrade level |

---

### type=map → citizens (nested)
**Source:** `getCitizensData()` (line 716)

**Default fields:** `id, name, isGhost, homeMessage, avatar, job, x, y`

Returns array of living citizens (uses `getUserData` per citizen).

---

### type=map → zones (nested)
**Source:** `getZonesData()` (line 1779)

**Default fields:** `x, y, nvt, exc, tag, danger`

| Field | Type | Description |
|---|---|---|
| `x`, `y` | int | Zone coordinates |
| `nvt` | int | 1 = not visited today |
| `exc` | int | 1 = force-regenerated |
| `tag` | int/null | Zone tag reference |
| `danger` | int | 0=safe, 1=low (1-2z), 2=med (3-5z), 3=high (6+z) |
| `details` | object | `{z: zombie_count, h: hero_cp, dried: bool}` |
| `items` | array | Floor items (only if user is in this zone) |
| `building` | object | Ruin data: `{type, name, desc, dig, camped, dried}` |

---

### type=items
**Source:** `getPrototypesAPI("items")` → `getItemPrototypesData()` (line 2204)

**Params:** `fields`, `filters` (icon names), `languages`
**Default fields:** `img, name`

Returns all item prototypes (keyed by internal name):
```json
{
  "item_wood2_#00": {"img": "item/item_wood2.gif", "name": "Wooden plank"},
  ...
}
```

**Available fields:** `id, img, uid, name, desc, cat, heavy, deco, guard`

---

### type=buildings
**Source:** `getPrototypesAPI("buildings")` → `getBuildingPrototypesData()` (line 2226)

**Default fields:** `img, name`

Returns all building prototypes (keyed by internal name).

**Available fields:** `id, img, name, desc, pa, paCurrent, maxLife, breakable, def, hasUpgrade, rarity, rarityCurrent, temporary, parent, order, difficulty, resources, resourcesCurrent`

---

### type=ruins
**Source:** `getPrototypesAPI("ruins")` → `getRuinPrototypesData()` (line 2270)

**Default fields:** `img, name`

**Available fields:** `id, img, name, desc, explorable`

---

### type=pictos
**Source:** `getPrototypesAPI("pictos")` → `getPictoPrototypesData()` (line 2248)

**Default fields:** `img, name`

**Available fields:** `id, img, name, desc, community, rare`

---

### GET /api/x/json/townlist
**Auth:** `userkey` + `appkey` (fefe not allowed)
**Source:** `api_json_townlist()` (line 186)

**Params:**
| Param | Description |
|---|---|
| `season` | Season number, `b` for beta, `a` for all (default: current season) |
| `language` | Filter by language code |

Returns:
```json
{"towns": [123, 456, 789]}
```

Array of town ranking IDs (not town IDs — these are `TownRankingProxy.id`).

---

### GET /api/x/json/towns
**Auth:** `userkey` + `appkey` (fefe not allowed)
**Source:** `api_json_town()` (line 193)

**Params:**
| Param | Description |
|---|---|
| `ids` | Comma-separated town IDs (max 50) |
| `fields` | SURLL field selection (default: `id, day, score`) |
| `languages` | SURLL language selection |

Returns ranking information per town.

**Available fields:** `id, mapId, day, mapName, language, season, phase, v1, score, citizens(.id|.name|.survival|...)`

---

## MCP-Relevant Endpoint Summary

For our read-only AI Town Advisor, the priority endpoints are:

| Priority | Endpoint | MCP Tool | What it provides |
|---|---|---|---|
| **P0** | `map` (with city.bank) | `get_bank_inventory` | Bank items |
| **P0** | `map` (with city.defense) | `get_town_defense` | Defense breakdown + total |
| **P0** | `map` (with city.estimations) | `get_attack_estimation` | Tonight's zombie count estimate |
| **P1** | `map` (with city) | `get_town_status` | Water, door, chaos, day |
| **P1** | `map` (with citizens) | `get_citizens` | Who's alive, where they are, jobs |
| **P1** | `map` (with zones) | `get_map` | Zone danger, ruins, items |
| **P1** | `map` (with city.buildings/chantiers) | `get_buildings` | Built + under construction |
| **P2** | `map` (with city.news) | `get_gazette` | Last night's attack report |
| **P2** | `items` | `get_item_catalogue` | Item database for lookups |
| **P2** | `me` | `get_my_status` | Current user's town, position, job |
| **P3** | `buildings` (proto) | `get_building_catalogue` | Building database |
| **P3** | `map` (with city.upgrades) | `get_upgrades` | Building upgrade status |
| **P3** | `map` (with expeditions) | `get_expeditions` | Planned expedition routes |

All town-specific data can be fetched via a single `map` call with appropriate `fields` — the SURLL syntax lets us request exactly the nested data we need in one request.
