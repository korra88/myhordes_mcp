# Official MyHordes Rules for External Apps & Scripts

Translated from the in-game help pages (German originals in the source templates at
`templates/ajax/help/use_of_external_sites.html.twig` and
`templates/ajax/help/use_of_external_scripts.html.twig`).

---

## Rules for External Sites & Applications

Source: `/jx/help/use_of_external_sites`

1. **Never ask for MyHordes login credentials.** You must not ask players for their MyHordes username/password on your site.

2. **Clearly state you are unofficial.** Your site must be clearly recognizable as not officially part of MyHordes.

3. **Distinct design.** Your site's design must clearly differ from MyHordes so users always know they're not on a MyHordes subpage.

4. **No automated/scheduled data polling.** You must not use automated scripts for regular data synchronization with the API (no cron jobs, no automated tasks).

5. **Attribute graphics.** If you use MyHordes graphics or content, you must credit the source and the rights of the author/artist.

6. **API-only data access.** Your application must orient itself around the APIs provided by the game. Both XML and JSON APIs are available and accessible with the same tokens.

---

## Rules for External Scripts (Client-Side)

Source: `/jx/help/use_of_external_scripts`

### Commercial Prohibition
- Scripts (or individual features) must **under no circumstances** be sold commercially.

### General Rules
- Scripts must describe their functionality in a user-understandable way **before** installation.
- Scripts must not display info or perform actions unrelated to MyHordes (no ads, no crypto mining).
- Scripts must not block or hide MyHordes features (warning dialogs are OK if dismissable).
- Script usage must not degrade the experience for players without the script.

### Automation
- Scripts **must not automate general gameplay**. Specifically forbidden:
  - **Making decisions for the player** (e.g., auto-drinking water after 10 steps).
  - **Receiving and executing external commands** (e.g., auto-investing AP in recommended construction sites).
- "Macro" shortcuts combining similar sequential actions are allowed, as long as individual actions remain individually triggerable.
- **Scripts must be conservative with server resources. Excessive request sending must be avoided.**

### Data Collection & Transmission
- Sending data to a server **must not be automated** — it may only happen when the player clicks a clearly labeled button.
- Only data **currently visible to the player** may be transmitted (no collecting data during movement for later bulk upload).
- **Personal information** (email, password, session tokens) and **player communications** (forum posts, PMs) must **never** be transmitted.
- Player secret keys may only be sent to the external application they belong to.
- **Secret roles** (e.g., ghoul status, forum moderator status) must never be transmitted.
- Data not available via the External API that is shared with other players must also be manually enterable (without the script) and must be falsifiable by players.

---

## Impact on Our MCP Server

### What these rules mean for us

| Rule | Impact | Our compliance |
|---|---|---|
| No automated polling (cron) | We must NOT poll the API on a schedule. Requests only on user action. | MCP tools are invoked on-demand by the LLM when the user asks. No background polling. Compliant. |
| No login credentials | We use `userkey`+`appkey` only, never username/password. | Compliant. |
| Read-only | Rules explicitly forbid automation of gameplay actions. | Our server is strictly read-only by design. Compliant. |
| Conservative with server resources | Minimize API calls; don't spam. | We should batch fields via SURLL and consider short-lived caching within a session. |
| No secret role data | We must not expose ghoul status or similar hidden info. | The external API already filters this server-side, but we should be mindful if we ever parse HTML. |
| Unofficial branding | Must be clear we're not official. | README and tool descriptions already state this is a fan project. |
| No personal data leakage | Keys stay in `.env`, never logged or transmitted elsewhere. | Keys are loaded from env vars, never included in tool responses. |

### Key constraint we hadn't fully accounted for

**No automated/scheduled data polling.** This is the most important rule we hadn't explicitly addressed. Our MCP architecture is naturally compliant (tools fire only when the LLM invokes them in response to user questions), but we must ensure we **never** add background refresh, caching cron, or periodic polling. Every API call must be a direct result of a user query.

### Recommendation

Add a comment block in `main.py` documenting the no-automation constraint so future contributors don't accidentally add polling:

```python
# IMPORTANT: MyHordes rules prohibit automated/scheduled API polling.
# All API calls must be triggered by explicit user queries via MCP tools.
# Never add cron jobs, background refresh, or periodic data fetching.
```
