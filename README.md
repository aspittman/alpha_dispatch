# Driver Dispatch Intelligence

Driver Dispatch Intelligence is a standalone, personal decision-support tool for a Utah Uber/Lyft driver. It is **not affiliated with Uber or Lyft**, is not an official dispatch system, and does not claim to predict future surge pricing. It ranks public leading indicators, explains its assumptions, and keeps opportunity and data confidence separate.

## What V1 does

- Collects Ticketmaster, SeatGeek, manual, and static holiday events with cached HTTP requests, retries, timeouts, and graceful source failure.
- Normalizes and conservatively deduplicates events while retaining attribution. Borderline matches are left separate for review.
- Adds known venue capacity, estimated attendance (explicitly low-confidence), and NWS hourly weather when coordinates are available.
- Builds category-specific arrival, departure, and secondary windows.
- Scores opportunity and confidence separately, applies hard safety/configuration rules, resolves conflicts, and caps weekly hours.
- Produces HTML and plain-text weekly reports and logs actual sessions with earnings metrics.
- Includes inactive extension points for official calendars and future airport data. Airport intelligence, live traffic, machine learning, navigation, and mobile features are intentionally out of scope.

## Setup

Python 3.10+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add Ticketmaster and SeatGeek credentials to `.env`. NWS does not require a key, but set `NWS_USER_AGENT` to a value containing a way to contact you. Edit YAML files under `config/`; secrets belong only in `.env`. Add manually verified events to `data/manual_events.yaml`. Unknown values should be `null`, not guesses.

## Commands

```bash
python main.py weekly-report
python main.py weekly-report --no-refresh
python main.py weekly-report --email
python main.py collect-events
python main.py score-events
python main.py show-top --limit 5
python main.py backfill-week 2026-07-13
python main.py test-sources
python main.py log-session --start 2026-07-17T18:00:00-06:00 --end 2026-07-18T00:00:00-06:00 --gross 180 --miles 110 --fuel 22 --trips 12 --event "Example concert"+```

Reports are written to `reports/output/`. The SQLite database defaults to `data/dispatch.db`. Missing API credentials appear as source failures but do not prevent manual/static data from generating a report.

## Weekly cron

Run every Thursday at 9:00 AM Mountain time (the host should use `America/Denver`):

```cron
CRON_TZ=America/Denver
0 9 * * 4 cd /absolute/path/to/alpha_dispatch && /absolute/path/to/alpha_dispatch/.venv/bin/python main.py weekly-report >> data/cron.log 2>&1
```

Use `--email` only after configuring SMTP variables and `DISPATCH_EMAIL_TO`. Keep execution low-frequency and comply with every source's terms. The placeholders for local calendars are designed for documented API, JSON, RSS, or iCal feeds before considering permitted HTML extraction; they do not bypass access controls.

## Scoring and safety

All weights are visible in `config/scoring.yaml`; venue assumptions are in `config/venues.yaml`. Attendance inferred from capacity is marked at low confidence. Opportunity is discounted by confidence so incomplete events do not look artificially precise. Severe weather, canceled/postponed events, excessive distance, missing date/location, permitted hours, attendance minimums, and score thresholds can suppress an item.

Staging text is general guidance only. Never park illegally, block traffic, trespass, wait roadside unsafely, enter restricted areas, or violate platform, airport, venue, or local rules. Confirm event times, closures, and current weather before acting.

## Tests

Tests use only fixtures—never live APIs:

```bash
pytest
```

## Adding an official Utah calendar

Create an adapter under `driver_dispatch/sources/local_calendars/` implementing `EventSource.collect(start, end) -> list[Event]`. Prefer, in order: official API, JSON, RSS, iCal, embedded structured data, then explicitly permitted low-frequency HTML. Register it in `DispatchService.sources`, add fixture-based parsing tests, and preserve the official page URL and raw source data.
