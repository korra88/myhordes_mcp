# MyHordes Source Map

Quick-reference for navigating the game source at `myhordes-docker/myhordes/`.

## Directory Layout

```
myhordes/
├── src/
│   ├── Controller/
│   │   ├── API/                  # External-facing API (our primary interest)
│   │   │   ├── CoreController.php        # Abstract base for all API controllers
│   │   │   ├── JSONv1Controller.php      # JSON API v1 (2300 lines, most complete)
│   │   │   ├── XMLv1Controller.php       # XML API v1 (legacy)
│   │   │   └── XMLv2Controller.php       # XML API v2 (with caching)
│   │   ├── REST/                 # Internal REST endpoints (browser game UI)
│   │   │   ├── Game/             # Game logic (inventory, map, buildings, door)
│   │   │   ├── User/             # User settings, soul, stats
│   │   │   └── Admin/            # Admin REST endpoints
│   │   ├── ExternalController.php        # API documentation pages
│   │   ├── Town/                 # Town page controllers
│   │   └── Soul/                 # User profile controllers
│   │
│   ├── Entity/                   # Doctrine ORM entities (~150 files)
│   │   ├── Town.php              # Central aggregate: citizens, bank, zones, buildings
│   │   ├── Citizen.php           # Player in a town: inventory, home, zone, status
│   │   ├── Inventory.php         # Polymorphic: bank, citizen bag, chest, zone floor
│   │   ├── Item.php              # Item instance (count, broken, poison)
│   │   ├── ItemPrototype.php     # Item template (name, icon, properties, category)
│   │   ├── Building.php          # Built structure (complete, level, hp, defense)
│   │   ├── BuildingPrototype.php # Building template (resources, defense, upgrades)
│   │   ├── Zone.php              # Map tile (x, y, zombies, floor items, ruin)
│   │   ├── ZonePrototype.php     # Ruin type template
│   │   ├── CitizenHome.php       # House (chest, upgrades, defense)
│   │   ├── ExternalApp.php       # Registered external application
│   │   ├── ExternalAccessTokens.php
│   │   └── ExternalAPIUsageRecord.php
│   │
│   ├── Repository/               # Doctrine repositories (~170 files)
│   │   ├── TownRepository.php    # findOpenTown(), findByNameContains()
│   │   ├── CitizenRepository.php # findInTown(), findActiveByUser(), findOneByRoleAndTown()
│   │   └── ExternalAppRepository.php
│   │
│   ├── Service/                  # Business logic (~50 services)
│   │   ├── TownHandler.php       # Town operations, defense calc, building management
│   │   ├── CitizenHandler.php    # Citizen state, wounds, skills
│   │   ├── InventoryHandler.php  # Item operations across inventory types
│   │   ├── ZoneHandler.php       # Zone/map operations
│   │   ├── GazetteService.php    # Daily news / gazette rendering
│   │   ├── ConfMaster.php        # Town configuration provider
│   │   └── TimeKeeperService.php # Attack timing, day/night cycle
│   │
│   ├── Structures/               # Plain data objects
│   │   ├── TownDefenseSummary.php # Defense breakdown (base, buildings, items, etc.)
│   │   ├── BankItem.php          # Item + count wrapper
│   │   ├── TownConf.php          # Town configuration values
│   │   └── HomeDefenseSummary.php
│   │
│   ├── Annotations/
│   │   └── ExternalAPI.php       # Attribute: user, app, cost, fefe, api
│   │
│   ├── Enum/
│   │   ├── ExternalAPIInterface.php  # GENERIC=0, JSONv1=1001, XMLv1=2001, XMLv2=2002
│   │   └── ExternalAPIError.php      # UserKeyNotFound/Invalid, AppKeyNotFound/Invalid, etc.
│   │
│   └── EventSubscriber/
│       └── APIRequestListener.php    # Auth + rate limiting for external APIs
│
├── config/
│   ├── routes.yaml               # Attribute-based routing from src/Controller/
│   └── services.yaml             # Service definitions
│
├── templates/
│   └── ajax/public/
│       ├── jsonapidocs.html.twig # JSON API documentation template
│       └── xmlapidocs.html.twig  # XML API documentation template
│
└── translations/                 # i18n files (de, en, fr, es)
```

## Data Model Relationships

```
Town (central aggregate)
├── citizens: Collection<Citizen>
│   ├── inventory: Inventory (personal bag)
│   ├── home: CitizenHome
│   │   ├── chest: Inventory
│   │   └── citizenHomeUpgrades: Collection<CitizenHomeUpgrade>
│   ├── profession: CitizenProfession
│   ├── roles: Collection<CitizenRole>  (guide, shaman, cata)
│   ├── status: Collection<CitizenStatus>
│   └── zone: Zone (current location, null = in town)
├── bank: Inventory (shared town storage)
│   └── items: Collection<Item>
│       └── prototype: ItemPrototype
├── buildings: Collection<Building>
│   ├── prototype: BuildingPrototype
│   │   └── resourceSets → BuildingConstructionResourceSet → entries
│   └── inventory: Inventory (building-specific storage)
├── zones: Collection<Zone>  (the map)
│   ├── floor: Inventory (ground items)
│   ├── prototype: ZonePrototype (ruin type, if any)
│   ├── citizens: Collection<Citizen> (who is here)
│   └── ruinZones: Collection<RuinZone>
├── zombieEstimations: Collection<ZombieEstimation>
├── gazettes: Collection<Gazette>
├── season: Season
├── type: TownClass (RNE, RE, PANDE, custom)
└── attackSchedule: AttackSchedule
```

## Key Entity Properties

### Town
| Property | Type | Notes |
|---|---|---|
| name | string | Town name |
| language | string | de, en, fr, es |
| population | int | Max citizens |
| day | int | Current game day |
| well | int | Water rations remaining |
| door | bool | Town gate open/closed |
| chaos | bool | Chaos mode (hides citizen positions) |
| devastated | bool | Town is devastated |
| baseDefense / soulDefense | int | Defense values |
| bonusScore | int | Bonus ranking points |

### Citizen
| Property | Type | Notes |
|---|---|---|
| alive | bool | |
| ap | int | Action points |
| banished | bool | |
| ghulHunger | int | Ghoul mechanic |
| survivedDays | int | |
| profession | CitizenProfession | Job class |
| zone | Zone | null = in town |

### Item / ItemPrototype
| Property | Type | Notes |
|---|---|---|
| Item.count | int | Stack quantity |
| Item.broken | bool | Damaged state |
| Item.poison | enum | Poison type |
| Proto.name | string | Internal ID (e.g., `item_wood2_#00`) |
| Proto.icon | string | Asset reference |
| Proto.heavy | bool | Encumbrance |
| Proto.watchpoint | int | Night watch value |
| Proto.properties | Collection | Tags: `defence`, etc. |

### Building / BuildingPrototype
| Property | Type | Notes |
|---|---|---|
| Building.complete | bool | Finished construction |
| Building.level | int | Upgrade level |
| Building.hp | int | Current hitpoints |
| Building.defense | int | Defense contribution |
| Proto.defense | int | Base defense value |
| Proto.maxLevel | int | Max upgrade level |
| Proto.impervious | bool | Cannot be destroyed |
| Proto.temp | bool | Temporary building |

### Zone
| Property | Type | Notes |
|---|---|---|
| x, y | int | Coordinates (0,0 = town center) |
| zombies | int | Current zombie count |
| discoveryStatus | int | None/Past/Current |
| buryCount | int | Sandpile depth (buried ruin) |
| digs | int | Remaining dig attempts |
| prototype | ZonePrototype | Ruin type (if any) |
