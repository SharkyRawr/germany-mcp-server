# Germany MCP Server

MCP-Server der AI-Agents Zugriff auf deutsche Behörden-Daten gibt — 16 Tools in 10 Kategorien, kostenlos nutzbar. Bundestag DIP benötigt einen API-Key.

[![germany-mcp-server MCP server](https://glama.ai/mcp/servers/AiAgentKarl/germany-mcp-server/badges/card.svg)](https://glama.ai/mcp/servers/AiAgentKarl/germany-mcp-server)

## 16 Tools in 10 Kategorien

### Verkehr (Autobahn)
- `autobahn_baustellen` — Aktuelle Baustellen auf einer Autobahn
- `autobahn_warnungen` — Staus und Verkehrswarnungen
- `autobahn_sperrungen` — Gesperrte Abschnitte
- `autobahn_ladestationen` — E-Auto-Ladestationen entlang einer Autobahn

### Wetter (DWD)
- `wetter_aktuell` — Aktuelles Wetter an einem Ort (30+ deutsche Städte vordefiniert)
- `wetter_warnungen` — DWD-Unwetterwarnungen (Sturm, Gewitter, Hitze etc.)

### DWD-Wetterwarnungen (NEU in v0.2.0)
- `get_german_weather_warnings` — Amtliche Wetterwarnungen direkt vom DWD (Sturm, Starkregen, Glatteis, Hitze). Filtern nach Bundesland möglich.

### Katastrophenwarnungen
- `nina_warnungen` — NINA/BBK: Hochwasser, Unwetter, Stromausfälle, Brände

### Energie (SMARD)
- `strom_erzeugung` — Stromerzeugung nach Energieträger (Wind, Solar, Kohle, Gas)
- `stromverbrauch` — Aktueller Stromverbrauch und Trend

### Energiepreise (NEU in v0.2.0)
- `get_energy_prices` — Deutsche Day-Ahead-Strompreise. 14-Tage-Verlauf mit Trend. Gaspreise sind derzeit nicht verfügbar.

### Politik (Bundestag)
- `bundestag_suche` — Gesetzentwürfe und Vorgänge durchsuchen
- `bundestag_aktivitaeten` — Letzte parlamentarische Aktivitäten

### Gesundheit
- `pollenflug` — Pollenflug-Vorhersage für 27 Regionen (Birke, Gräser, Hasel etc.)

### Statistik (NEU in v0.2.0)
- `get_destatis_data` — Offizielle Destatis-Statistiken: Bevölkerung, BIP, Arbeitslosenquote, Inflation, Erwerbstätigkeit. Standardmäßig die letzten fünf Kalenderjahre.

### Recht (NEU in v0.2.0)
- `search_german_laws` — 6000+ Bundesgesetze durchsuchen (Titel, Abkürzung). Direkt-Links zu gesetze-im-internet.de.

## Installation

Benötigt Python 3.11+ und das MCP Python SDK 2.x (wird automatisch installiert).

```bash
pip install germany-mcp-server
```

Oder direkt von GitHub:

```bash
pip install git+https://github.com/AiAgentKarl/germany-mcp-server.git
```

## Docker

Das Image verwendet `python:3-slim-trixie` (aktuelles stabiles Python auf Debian
Trixie) und die stabilen, in `uv.lock` festgehaltenen Abhängigkeiten.
`docker build --pull` aktualisiert das Basisimage. Python-Abhängigkeiten mit
`uv lock --upgrade` aktualisieren; die uv-Version im Dockerfile separat anheben.

```bash
docker build --pull -t germany-mcp-server .
docker run --rm --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -p 127.0.0.1:8000:8000 -e BUNDESTAG_API_KEY germany-mcp-server
```

MCP-Endpunkt: `http://localhost:8000/mcp` (Streamable HTTP, stateless).
Healthcheck: `http://localhost:8000/healthz`. Der Prozess läuft als UID/GID
10001, benötigt keine Volumes und installiert beim Start keine Pakete.
Der Gesetzesindex bleibt ein verwerfbarer Cache pro Container.

`PORT` ändert den internen Port (Standard: 8000); das Port-Mapping entsprechend
anpassen. Ohne `BUNDESTAG_API_KEY` bleiben alle anderen Tools verfügbar.
Für einen Reverse Proxy `MCP_ALLOWED_HOSTS` (z. B. `mcp.example.org`) und bei
Browser-Zugriffen `MCP_ALLOWED_ORIGINS` (z. B. `https://mcp.example.org`)
als kommaseparierte Listen setzen. Standardmäßig sind lokale Hosts erlaubt.
Der Server enthält keine eingehende Authentifizierung: externe Freigabe über
einen Gateway mit TLS und Zugriffskontrolle vornehmen.

Für lokale MCP-Clients mit stdio:

```bash
docker run --rm -i --health-cmd=none -e MCP_TRANSPORT=stdio germany-mcp-server
```

## Nutzung mit Claude Code

`.mcp.json` im Projektverzeichnis:

```json
{
  "mcpServers": {
    "germany": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "src.server"]
    }
  }
}
```

Alternativ mit `uvx` (kein lokales Install nötig):

```json
{
  "mcpServers": {
    "germany": {
      "type": "stdio",
      "command": "uvx",
      "args": ["germany-mcp-server"]
    }
  }
}
```

## Beispiel-Abfragen

```
"Wie ist das Wetter in München?"
"Gibt es Unwetterwarnungen in Bayern?"
"Zeig mir die Arbeitslosenquote der letzten 5 Jahre"
"Suche nach Gesetzen zum Thema Datenschutz"
"Was ist der aktuelle Börsenstrompreis?"
"Gibt es Baustellen auf der A7?"
"Wie hoch ist die aktuelle Pollenbelastung in NRW?"
"Zeig mir das BIP pro Kopf für 2023"
```

## Datenquellen

Alle APIs sind **kostenlos** nutzbar. Nur Bundestag DIP benötigt einen API-Key:

| API | Quelle | Daten |
|-----|--------|-------|
| Autobahn | verkehr.autobahn.de | Verkehr, Baustellen, Ladestationen |
| Bright Sky | brightsky.dev (DWD) | Wetter, Temperatur, Niederschlag |
| DWD Warnungen | dwd.de | Amtliche Wetterwarnungen |
| NINA | warnung.bund.de | Katastrophenwarnungen (5 Kanäle) |
| SMARD | smard.de | Energiemarkt, Stromerzeugung, Preise |
| Bundestag DIP | dip.bundestag.de | Parlamentarische Daten |
| DWD Pollenflug | opendata.dwd.de | Pollenbelastung, 27 Regionen |
| Eurostat/Destatis | ec.europa.eu/eurostat | BIP, Bevölkerung, Inflation, Arbeitsmarkt |
| Gesetze-im-Internet | gesetze-im-internet.de | 6000+ Bundesgesetze und Verordnungen |

## Bundestag API-Key

Für `bundestag_suche` und `bundestag_aktivitaeten` muss `BUNDESTAG_API_KEY` in der Umgebung des Serverprozesses gesetzt sein. Ohne Key geben diese Tools einen Konfigurationsfehler zurück; alle anderen Tools bleiben nutzbar.

```bash
# Bundestag DIP API (kostenlos registrierbar bei dip.bundestag.de)
export BUNDESTAG_API_KEY=dein-key-hier
```

## Changelog

### Unveröffentlicht
- Migration auf MCP Python SDK 2.x.
- Wetterwarnungen lesen die lokalisierten Bright-Sky-Felder (Deutsch, ersatzweise Englisch).
- Gaspreisabfragen geben einen Fehler zurück: Die bisherige SMARD-Reihe 4996 enthält belgische Strompreise, keine Gaspreise.
- Bundestag DIP erfordert einen API-Key; fehlende oder abgelehnte Zugangsdaten liefern klare Fehler.

### v0.2.0 (April 2026)
- 4 neue Tools: `get_destatis_data`, `search_german_laws`, `get_german_weather_warnings`, `get_energy_prices`
- 3 neue Clients: Destatis/Eurostat, Gesetze-im-Internet, DWD-Warnungen
- Energiepreise-Modul (Strom- und Gaspreise)
- 16 Tools in 10 Kategorien (vorher 12 in 6)

### v0.1.2
- Initiale Version mit 12 Tools

## Datenqualität und Fehlerbehandlung

- Stromerzeugung enthält alle zwölf erfassten Energieträger für denselben neuesten verfügbaren Zeitstempel. Fehlende Werte werden als `null` ausgewiesen; unvollständige Gesamtsummen und Prozentanteile werden nicht berechnet. `vollstaendig` und `fehlende_traeger` zeigen Datenlücken an.
- Energiepreise verwenden heute und die 13 vorherigen Kalendertage in `Europe/Berlin`, auch über Datenblockgrenzen und Zeitumstellungen hinweg. `zeitraum_von`, `zeitraum_bis`, `anzahl_tage_mit_daten` und `vollstaendig` beschreiben die Abdeckung. Kennzahlen basieren bei Lücken nur auf verfügbaren Tagen; ältere Werte füllen keine Lücken auf.
- Bundestag-Clientmethoden begrenzen die zurückgegebenen Dokumente auf `limit` (1–100). Die Gesamtzahl der Treffer bleibt erhalten.
- Der Gesetzesindex wird eine Stunde zwischengespeichert. Gleichzeitige Anfragen teilen eine Aktualisierung; bei einem Aktualisierungsfehler werden abgelaufene Daten nicht als aktuell ausgegeben.
- Alle HTTP-Antworten werden beim Lesen auf 16 MiB und 30 Sekunden Gesamtdauer begrenzt. Der Client fordert unkomprimierte Antworten an und lehnt unerwartete Kompression ab. Weiterleitungen bleiben auf denselben Ursprung beschränkt.
- Toolfehler geben keine rohen Ausnahmeinformationen zurück. Die Fehlerprotokollierung nennt nur die Ausnahmeklasse.

Die Grenzwerte und die Cache-Dauer stehen in `src/config.py`.

## Tests

Git-Hook einmal pro Checkout aktivieren (systemweit installiertes `black` muss im `PATH` liegen):

```bash
./scripts/setup-hooks.sh
```

Der Pre-Commit-Hook formatiert Python-Dateien mit `black .`. Bei ungestagten Python-Änderungen bricht er ab: Änderungen prüfen, mit `git add` stagen und erneut committen. Der Hook staged keine Dateien automatisch.

Nach der Installation lassen sich die Regressionstests ohne externe API-Aufrufe ausführen:

```bash
python -m unittest discover -s tests -v
```

## Lizenz

MIT

---

## More MCP Servers by AiAgentKarl

| Category | Servers |
|----------|---------|
| Blockchain | [Solana](https://github.com/AiAgentKarl/solana-mcp-server) |
| Data | [Weather](https://github.com/AiAgentKarl/weather-mcp-server) · [Germany](https://github.com/AiAgentKarl/germany-mcp-server) · [Agriculture](https://github.com/AiAgentKarl/agriculture-mcp-server) · [Space](https://github.com/AiAgentKarl/space-mcp-server) · [Aviation](https://github.com/AiAgentKarl/aviation-mcp-server) · [EU Companies](https://github.com/AiAgentKarl/eu-company-mcp-server) |
| Security | [Cybersecurity](https://github.com/AiAgentKarl/cybersecurity-mcp-server) · [Fraud Prevention](https://github.com/AiAgentKarl/fraud-prevention-mcp-server) · [Policy Gateway](https://github.com/AiAgentKarl/agent-policy-gateway-mcp) · [Audit Trail](https://github.com/AiAgentKarl/agent-audit-trail-mcp) |
| Agent Infra | [Memory](https://github.com/AiAgentKarl/agent-memory-mcp-server) · [Directory](https://github.com/AiAgentKarl/agent-directory-mcp-server) · [Hub](https://github.com/AiAgentKarl/mcp-appstore-server) · [Reputation](https://github.com/AiAgentKarl/agent-reputation-mcp-server) · [Insurance](https://github.com/AiAgentKarl/agent-insurance-mcp-server) |
| Research | [Academic](https://github.com/AiAgentKarl/crossref-academic-mcp-server) · [LLM Benchmark](https://github.com/AiAgentKarl/llm-benchmark-mcp-server) · [Legal](https://github.com/AiAgentKarl/legal-court-mcp-server) · [Patent](https://github.com/AiAgentKarl/patent-mcp-server) |

[Full catalog (55+ servers)](https://github.com/AiAgentKarl)
