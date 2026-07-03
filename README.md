# ShipShow für Home Assistant

Benutzerdefinierte Home-Assistant-Integration für die dokumentierte externe ShipShow-API.

## Funktionen

- Einrichtung über den Home-Assistant-Konfigurationsdialog
- Nutzt den öffentlichen Endpunkt `GET /external/getTrackings`
- Unterstützt alle dokumentierten Abfrageoptionen: Kategorie, Suche, Statusfilter, Limit, Offset über Pagination, Sortierfeld und Sortierreihenfolge
- Automatische Pagination bis zur konfigurierten Seitengrenze
- Globale ShipShow-Entitäten an einem eigenen `ShipShow`-Gerät
- Automationsfreundliche Sensoren `ShipShow Aktuelle Lieferungen` und `ShipShow Lieferübersicht`
- Pro Sendung: Status, letzte Meldung, geplante Lieferung und Tage bis Lieferung
- Pro Sendung: Binärsensoren für Zugestellt, In Zustellung und Problem
- Pro Sendung: Kalender-Entitäten für geplante Liefertermine
- Dashboard-Attribute für Auto Entities: `shipshow_scope`, `shipshow_dashboard_group`, `shipshow_entity_group`, `shipshow_entity_role`
- Diagnose mit ausgeblendetem API-Schlüssel
- HACS-Metadaten und GitHub-Validierungsworkflows

## Voraussetzungen

- ShipShow-Pro-Abo
- API-Schlüssel aus der ShipShow-App unter Einstellungen > API-Schlüssel

## Installation mit HACS

1. Dieses Repository in HACS als benutzerdefiniertes Repository hinzufügen.
2. Kategorie `Integration` auswählen.
3. `ShipShow` installieren.
4. Home Assistant neu starten.
5. Einstellungen > Geräte & Dienste > Integration hinzufügen > ShipShow öffnen.

## Optionen

Das Abrufintervall stellst du in Home Assistant hier ein:

Einstellungen > Geräte & Dienste > ShipShow > Konfigurieren > Abrufintervall

Der Wert wird in Sekunden angegeben. Der Mindestwert ist 60 Sekunden, passend zur Empfehlung der öffentlichen ShipShow-API. Nach dem Speichern lädt Home Assistant die Integration neu und der globale Sensor `ShipShow Abrufintervall` zeigt den aktiven Wert an.

## Namensschema

Globale Entitäten hängen am Gerät `ShipShow` und heißen zum Beispiel:

- `sensor.shipshow_lieferuebersicht`
- `sensor.shipshow_aktuelle_lieferungen`
- `sensor.shipshow_pakete_gesamt`
- `sensor.shipshow_in_zustellung`
- `sensor.shipshow_abrufintervall`

Neue Sendungs-Entitäten bekommen vorgeschlagene Entity-IDs nach diesem Schema:

- `sensor.shipshow_lieferung_<sendungsnummer>_status`
- `sensor.shipshow_lieferung_<sendungsnummer>_uebersicht`
- `sensor.shipshow_lieferung_<sendungsnummer>_letzte_meldung`
- `sensor.shipshow_lieferung_<sendungsnummer>_geplante_lieferung`
- `sensor.shipshow_lieferung_<sendungsnummer>_tage_bis_lieferung`
- `binary_sensor.shipshow_lieferung_<sendungsnummer>_zugestellt`
- `binary_sensor.shipshow_lieferung_<sendungsnummer>_in_zustellung`
- `binary_sensor.shipshow_lieferung_<sendungsnummer>_problem`

Bestehende Entity-IDs benennt Home Assistant aus Sicherheitsgründen nicht automatisch um. Die neuen Attribute sind aber auch bei bestehenden Entitäten vorhanden.

In Home Assistant ist jede Sendung ein eigenes Gerät. Die Entitäten heißen innerhalb der Sendung nur noch `Status`, `Letzte Meldung`, `Geplante Lieferung` usw. Dadurch vermeidet die Oberfläche doppelte Namen wie `AirTag Joybuy ShipShow Lieferung AirTag Joybuy ...`.

## Auto Entities

Alle Sendungs-Entitäten tragen diese Attribute:

- `shipshow_scope: lieferung`
- `shipshow_dashboard_group: shipshow_lieferungen`
- `shipshow_entity_group: shipshow_lieferung_<sendungsnummer>`
- `shipshow_entity_role: uebersicht`, `status`, `letzte_meldung`, `geplante_lieferung`, `tage_bis_lieferung`, `zugestellt`, `in_zustellung` oder `problem`

Beispiel für eine Auto-Entities-Karte, die alle Sendungs-Entitäten automatisch einsammelt:

```yaml
type: custom:auto-entities
card:
  type: entities
  title: ShipShow Lieferungen
filter:
  include:
    - attributes:
        shipshow_dashboard_group: shipshow_lieferungen
sort:
  method: attribute
  attribute: shipshow_entity_group
```

Beispiel für eine klickbare Sendungsübersicht:

```yaml
type: custom:auto-entities
card:
  type: entities
  title: ShipShow Lieferungen
  show_header_toggle: false
filter:
  include:
    - attributes:
        shipshow_dashboard_group: shipshow_lieferungen
        shipshow_entity_role: uebersicht
      options:
        secondary_info: last-changed
        tap_action:
          action: more-info
  exclude:
    - state: unavailable
sort:
  method: name
```

Beim Klick auf eine Sendung öffnet Home Assistant das Detailfenster des `Übersicht`-Sensors. Dort stehen die Sendungsdetails als Attribute, unter anderem `meldung`, `sendungsnummer`, `sendungsverfolgung_url`, `verlauf`, `stopps` und `rohdaten`, wenn ShipShow diese Daten liefert.

Globale ShipShow-Entitäten lassen sich so sammeln:

```yaml
type: custom:auto-entities
card:
  type: entities
  title: ShipShow Übersicht
filter:
  include:
    - attributes:
        shipshow_dashboard_group: shipshow_global
sort:
  method: name
```

## Push-Automation für Zustellung und Stopps

Die Integration feuert Home-Assistant-Events, damit eine einzige Automation für alle aktuellen und zukünftigen Sendungen reicht.

Events:

- `shipshow_lieferung_in_zustellung`: Wird ausgelöst, wenn eine Sendung in Zustellung geht.
- `shipshow_stopps_weniger`: Wird ausgelöst, wenn die verbleibenden Stopps kleiner werden.

Event-Daten:

- `titel`
- `sendungsnummer`
- `dienstleister`
- `status`
- `meldung`
- `sendungsverfolgung_url`
- `stopps_verbleibend`
- `vorherige_stopps` beim Event `shipshow_stopps_weniger`
- `benachrichtigung`: fertiger deutscher Push-Text

In Home Assistant legst du eine Automation mit zwei Event-Triggern an:

1. Einstellungen > Automationen & Szenen > Automation erstellen.
2. Trigger `Event` auswählen.
3. Event-Typ `shipshow_lieferung_in_zustellung` hinzufügen.
4. Zweiten Event-Trigger mit `shipshow_stopps_weniger` hinzufügen.
5. Als Aktion deinen Mobile-App-Benachrichtigungsdienst auswählen.
6. Als Nachricht kannst du `trigger.event.data.benachrichtigung` verwenden.

DHL- und Amazon-Stopps werden nur gemeldet, wenn ShipShow diese Informationen in der öffentlichen API-Antwort mitliefert. Die Integration durchsucht Carrier-Metadaten, Lieferfortschrittsmeldungen und die neuesten Verlaufseinträge nach Stopps.

## API-Hinweise

Die öffentliche API-Dokumentation unter [shipshow.net/api](https://www.shipshow.net/api) dokumentiert:

- Basis-URL: `https://api.shipshow.net/external/`
- Endpunkt: `GET /external/getTrackings`
- Authentifizierung: Query-Parameter `apikey`
- Empfohlenes Abrufintervall: nicht öfter als einmal pro Minute
- Maximale Seitengröße: 50

Diese Integration folgt dem öffentlichen API-Vertrag und nutzt keine internen ShipShow-Web-App-Endpunkte.
