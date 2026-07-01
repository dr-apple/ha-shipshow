# ShipShow for Home Assistant

Custom Home Assistant integration for the documented ShipShow External API.

## Features

- UI setup through Home Assistant config flow
- Uses the public `GET /external/getTrackings` endpoint
- Supports every documented query option: category, search, status filter, limit, offset through pagination, sort field, and sort order
- Automatic pagination up to a configurable page limit
- Account summary sensors
- Per-package status, message, delivery date, and days-until-delivery sensors
- Per-package delivered, out-for-delivery, and exception binary sensors
- Per-package delivery calendar entities
- Diagnostics with the API key redacted
- HACS metadata and GitHub validation workflows

## Requirements

- A ShipShow Pro subscription
- An API key generated in the ShipShow mobile app under Settings > API Keys

## Installation With HACS

1. Add this repository as a custom repository in HACS.
2. Select category `Integration`.
3. Install `ShipShow`.
4. Restart Home Assistant.
5. Go to Settings > Devices & Services > Add Integration > ShipShow.

## API Notes

The public API documentation at [shipshow.net/api](https://www.shipshow.net/api) documents:

- Base URL: `https://api.shipshow.net/external/`
- Endpoint: `GET /external/getTrackings`
- Authentication: `apikey` query parameter
- Recommended polling: no more than one request per minute
- Maximum page size: 50

This integration follows that public contract and does not use ShipShow's internal web-app endpoints.
