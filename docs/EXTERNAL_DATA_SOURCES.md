# External data sources

Reviewed 31 October 2026.

## Travel planner: Open-Meteo

Project Alpha uses Open-Meteo's official [Geocoding API](https://open-meteo.com/en/docs/geocoding-api) to resolve the destination entered by the user and the [Forecast API](https://open-meteo.com/en/docs) for seven days of daily weather. The app submits one lookup per deliberate trip search, caches the result for 30 minutes, applies request timeouts, and renders attribution. It does not scrape travel sites or claim venue availability.

Open-Meteo's [terms](https://open-meteo.com/en/terms) limit the free API to non-commercial use and specify CC BY 4.0 attribution. If Alpha is used commercially, switch to the provider's commercial plan or another source with appropriate terms. The forecast service does not guarantee completeness, uptime, or accuracy.

Location results are based on GeoNames, as documented by Open-Meteo. The itinerary activity catalog, prices, and accessibility details remain explicitly fictional and are not mixed with the live weather feed.

## Other tools

The other tools currently operate on generated sample data or user-provided local documents. A real CRM, ticketing system, procurement source, customer dataset, telemetry platform, or travel inventory requires a specific provider, authorized credentials, data permissions, and a field mapping. Alpha does not scrape unspecified websites or connect to personal accounts by guessing endpoints.
