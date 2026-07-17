# Driver Dispatch Intelligence

Driver Dispatch Intelligence is a standalone, personal decision-support tool for a Utah Uber/Lyft driver. It is **not affiliated with Uber or Lyft**, is not an official dispatch system, and does not claim to predict future surge pricing. It ranks public leading indicators, explains its assumptions, and keeps opportunity and data confidence separate.

## What V1 does

- Collects Ticketmaster, SeatGeek, manual, and static holiday events with cached HTTP requests, retries, timeouts, and graceful source failure.
- Normalizes and conservatively deduplicates events while retaining attribution. Borderline matches are left separate for review.
- Applies canonical venue aliases before matching and retains source conflicts for audit.
- Keeps venue capacity separate from attendance ranges and labels the estimate basis/confidence.
- Adds NWS hourly weather only for preliminary recommended windows, then rescores for demand and safety separately.
- Builds category-specific arrival, departure, and secondary windows.
- Scores opportunity and confidence separately, applies validation gates, merges overlapping/adjacent windows, and caps daily/weekly hours.
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
python main.py log-session --start 2026-07-17T18:00:00-06:00 --end 2026-07-18T00:00:00-06:00 --gross 180 --miles 110 --fuel 22 --trips 12 --event "Example concert"
```

Reports are written to `reports/output/`. The SQLite database defaults to `data/dispatch.db`. Missing API credentials appear as source failures but do not prevent manual/static data from generating a report.

## Weekly cron

Run every Thursday at 9:00 AM Mountain time (the host should use `America/Denver`):

```cron
CRON_TZ=America/Denver
0 9 * * 4 cd /absolute/path/to/alpha_dispatch && /absolute/path/to/alpha_dispatch/.venv/bin/python main.py weekly-report >> data/cron.log 2>&1
```

Use `--email` only after configuring SMTP variables and `DISPATCH_EMAIL_TO`. Keep execution low-frequency and comply with every source's terms. The placeholders for local calendars are designed for documented API, JSON, RSS, or iCal feeds before considering permitted HTML extraction; they do not bypass access controls.

## Scoring and safety

All weights are visible in `config/scoring.yaml`; canonical venue and staging data are in `config/venues.yaml`; optional-source states are in `config/feature_statuses.yaml`. Capacity-only attendance is a conservative range at low confidence and is never stored as confirmed attendance. Opportunity and confidence remain independent so upside cannot hide weak data. Severe weather, canceled/postponed events, excessive distance, missing date/location, permitted hours, freshness, and score thresholds can suppress an item.

Staging text is general guidance only. Never park illegally, block traffic, trespass, wait roadside unsafely, enter restricted areas, or violate platform, airport, venue, or local rules. Confirm event times, closures, and current weather before acting.

## Tests

Tests use only fixtures—never live APIs:

```bash
pytest
```

## Adding an official Utah calendar

Create an adapter under `driver_dispatch/sources/local_calendars/` implementing `EventSource.collect(start, end) -> list[Event]`. Prefer, in order: official API, JSON, RSS, iCal, embedded structured data, then explicitly permitted low-frequency HTML. Register it in `DispatchService.sources`, add fixture-based parsing tests, and preserve the official page URL and raw source data.
# Alpha Dispatch

Alpha Dispatch is independent, explainable rideshare planning software. It does not predict or guarantee earnings, tips, surge, or driver competition.

## Architecture

The existing application is a Python service organized around Pydantic models, configurable event-source adapters, normalization/enrichment, rule-based scoring, planning, SQLite persistence, and text/HTML reports. Live mobility extends those same seams:

- `driver_dispatch/adapters/` contains the UDOT Traffic and Google Routes clients.
- `driver_dispatch/mobility.py` combines route measurements, route-relevant incidents, operating preferences, and zone classifications.
- `config/operating_zones.yaml` owns verified city-center coordinates, radii, priorities, corridors, operational traffic thresholds, and user preferences.
- SQLite migrations store traffic runs, route snapshots, incidents, and zone recommendations.
- Weekly reporting retains event planning and adds `PLANNED MOBILITY CONDITIONS`; live modes create concise text reports.

Measured Google/UDOT conditions remain separate from Aaron's configurable parking, stopping, driving-complexity, and northbound-drift preferences.

## API setup

### UDOT Traffic

Request a developer key from the official UDOT Traffic developer/API page, accept its terms, and place the issued key only in local environment configuration. UDOT's API accepts the developer key as the `key` request parameter. Alpha Dispatch limits this adapter to at most ten calls in a rolling 60-second window.

### Google Maps Platform

In Google Cloud, create a project, enable billing, enable **Routes API**, and create an API key. Billing must be enabled for Routes API requests even when usage remains within a credit or no-cost allowance. Restrict the key to the Routes API and, where Google supports it for the deployment, to the appropriate application environment.

Compute Route Matrix usage is billed by route element: origins multiplied by destinations. Alpha Dispatch uses one origin and at most ten local destinations by default, caches duplicate comparisons, excludes distant zones from normal refreshes, and enforces a local request limit. Confirm current pricing and quota terms in Google's official documentation before enabling production use.

Never commit `.env` or credentials. A suitable local `.env` is:

```env
UDOT_API_KEY=
UDOT_API_BASE_URL=https://www.udottraffic.utah.gov/api/v2
UDOT_ENABLED=true
UDOT_CACHE_MINUTES=5

GOOGLE_ROUTES_API_KEY=
GOOGLE_ROUTES_ENABLED=true
GOOGLE_ROUTES_BASE_URL=https://routes.googleapis.com
GOOGLE_ROUTES_ROUTING_PREFERENCE=TRAFFIC_AWARE
GOOGLE_ROUTES_CACHE_MINUTES=5
GOOGLE_ROUTES_MAX_DAILY_REQUESTS=50
GOOGLE_ROUTES_MAX_DESTINATIONS_PER_CHECK=10
INCLUDE_DISTANT_ZONES_BY_DEFAULT=false

PLANNED_SHIFT_END=
DRIFT_PENALTY_INCREASE_LAST_90_MINUTES=true
```

`TRAFFIC_AWARE_OPTIMAL` is supported through `GOOGLE_ROUTES_ROUTING_PREFERENCE`, but should be reserved for an explicit high-value check because it can have different latency/cost characteristics. `TRAFFIC_AWARE` is the default.

## Running

```bash
python main.py --mode weekly
python main.py --mode pre_shift
python main.py --mode live_refresh --current-zone provo
python main.py --mode live_refresh --latitude 40.2338 --longitude -111.6585
```

The original CLI remains supported:

```bash
python main.py weekly-report
python main.py collect-events
python main.py show-top --limit 10
```

Use `--include-distant-zones` when a specific high-value northern opportunity warrants measuring discouraged zones. `--current-zone salt_lake_city` substantially removes Orem positioning distance by making Salt Lake the origin.

## Cost and freshness protections

- UDOT events and alerts: five-minute cache by default; conservative retries and rolling ten-call throttle.
- Google matrices: five-minute departure buckets and cache; one origin; configurable per-run destination cap.
- Persistent daily Google request counter in the mobility cache directory; no request is made after the local limit.
- Narrow Google field mask: duration, static duration, distance, indices, and route status only.
- Cache hit/miss and API-call statistics appear in structured logs/run summaries.
- Stale traffic is never silently treated as live. If a valid live cache is absent, the zone is `UNAVAILABLE`.

Google answers how long travel takes; UDOT can explain why. An incident is attached only when it is geographically near a zone or matches a configured origin-to-zone corridor. The system does not claim causation without overlap.

## Data and recommendations

Traffic severity uses configurable operational thresholds in `config/operating_zones.yaml`; they are not scientific facts. Zone results are `PREFER`, `ACCEPTABLE`, `AVOID`, or `UNAVAILABLE`. Closures, measured delay, positioning distance, configured zone priority, return direction, and user-observed preferences drive the result. Competition, expected earnings, and expected tips remain `Unknown`.

Traffic history is stored in:

- `traffic_check_runs`
- `route_snapshots`
- `traffic_incidents`
- `zone_recommendations`

Migration `003_traffic_intelligence.sql` is applied automatically. This history is intended for later comparison with Aaron's own driving sessions; no earnings model is implemented.

## Tests

All external calls are mocked in automated tests:

```bash
python -m pytest -q
```

## Failure behavior and limitations

If Google fails, UDOT conditions remain visible but destinations are unavailable. If UDOT fails, measured Google travel times remain usable and incident explanations are marked unavailable. If both fail, Alpha Dispatch does not invent a live recommendation. Weekly event reporting continues when mobility sources fail.

Current limitations include no live GPS integration, no turn-by-turn guidance, no camera-image analysis, approximate incident relevance without route polylines, no independently verified rideshare drift/competition data, and no earnings/surge/tip prediction. Return-home time is represented by positioning distance/preferences in this phase; a second reverse matrix is intentionally avoided to control cost.

Location inputs and traffic snapshots can reveal movement patterns. Keep the SQLite database, cache, and reports private; do not publish precise coordinates or commit generated personal data.

## Example output

See [weekly sample](docs/samples/weekly.txt), [pre-shift sample](docs/samples/pre_shift.txt), and [live-refresh sample](docs/samples/live_refresh.txt). These are illustrative mocked reports, not current traffic.
