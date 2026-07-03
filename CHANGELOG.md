# Changelog

## 0.8.0

- Fix duplicated delivery names in dashboard rows by letting the delivery device provide the package name and the entity provide only the field name.
- Keep status sensor attributes as the detailed shipment popup target for dashboard `more-info` actions.

## 0.7.0

- Fire `shipshow_lieferung_in_zustellung` when a delivery enters out-for-delivery status.
- Fire `shipshow_stopps_weniger` when the remaining stop count decreases.
- Include delivery title, tracking number, carrier, tracking URL, message, remaining stops, and previous stops in event data where available.
- Include a ready-to-send German `benachrichtigung` text in delivery event data.
- Document the event-based push notification automation setup.

## 0.6.0

- Make the polling interval option clearer in Home Assistant with German descriptions and the 60-second minimum.
- Add a global `ShipShow Abrufintervall` sensor that shows the currently active polling interval in seconds.
- Document where to change the polling interval in Home Assistant.

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
