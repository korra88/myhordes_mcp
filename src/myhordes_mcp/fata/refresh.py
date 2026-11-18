"""One refresh of the active town's files: `make town-refresh`, run by town-refresh.timer.

The only scheduled Fata request of this project (docs/camping-plan.md, Phase F; approved by
the Fata developer, requests carry our user agent). Two fixed runs a day, 00:25 and 01:30
Europe/Paris, for the active town only (towns/_current_town, else FATAMORGANA_TOWN_ID):

  00:25  the attack blocks updates, so the live fetch is the end state of day N
         (camping log input, town log check);
  01:30  if Fata already has day N+1, the town log closes day N and opens N+1 and the
         camping log judges the night; else nothing changes and the next user query does it.

One live fetch through the normal client (archive, CP log, town log, camping log). No
retry, no message to anyone, no game action. Never touches the MyHordes API.
"""

import asyncio
import os
import sys

from ..utils.config import resolve_town_id
from .client import fetch_town_data


async def _run() -> int:
    town = resolve_town_id(0)
    if isinstance(town, str):
        print(f"town-refresh: {town}")
        return 1
    data = await fetch_town_data(town)
    if data.get("error"):
        # Fata down or rate-limited: log and stop, the next user query catches up.
        print(f"town-refresh: town {town}: {data['error']}")
        return 0
    meta = data["meta"]
    note = meta.get("log_note") or "town log unchanged"
    print(f"town-refresh: town {town} day {meta.get('day')}, data {meta.get('data_time')}; {note}")
    return 0


def main() -> int:
    os.environ["USAGE_STATS_ORIGIN"] = "timer"   # utils/usage_stats.py: label the request
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
