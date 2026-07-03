# Changelog

## 0.5.0

- Add a global `ShipShow` device for account-level entities such as `ShipShow Lieferübersicht` and `ShipShow Aktuelle Lieferungen`.
- Introduce dashboard-friendly tracking names in the form `ShipShow Lieferung <Titel> - <Feld>`.
- Add Auto Entities attributes to every delivery entity: `shipshow_scope`, `shipshow_dashboard_group`, `shipshow_entity_group`, and `shipshow_entity_role`.
- Suggest stable entity ids for new deliveries, for example `sensor.shipshow_lieferung_<sendungsnummer>_status`.
- Document German naming and Auto Entities examples in the README.

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
