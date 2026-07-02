# Changelog

## 0.4.0

- Show all active deliveries directly in the visible `Lieferübersicht` sensor state.
- Fix Home Assistant entity names that could still be prefixed with `UndefinedType._singleton`.
- Keep Amazon/carrier stop support active when ShipShow exposes stop metadata in the API response.

## 0.3.0

- Fix entity names that showed `UndefinedType._singleton`.
- Rename sensors and setup/options text to German.
- Add visible `Lieferübersicht` text sensor in addition to the numeric `Aktuelle Lieferungen` overview sensor.
- Translate status values and overview attributes to German.

## 0.2.0

- Add `Active Deliveries` overview sensor for automations.
- Include compact current delivery attributes with next delivery, out-for-delivery list, exception flag, and stop counts when ShipShow exposes carrier stop metadata.
- Extract stop counts from carrier metadata and English/German tracking messages.

## 0.1.0

- Initial ShipShow Home Assistant integration.
