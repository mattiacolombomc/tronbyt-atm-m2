# tronbyt-atm-m2

Tronbyt / Pixlet app for commutes on the ATM Milano network: minutes to the
next departures, the connection if the trip has a change, and the arrival time.

Times are **scheduled**, not real time: ATM does not publish live data.
They come from the [Comune di Milano GTFS feed](https://dati.comune.milano.it/dataset/ds929-orari-del-trasporto-pubblico-locale-nel-comune-di-milano-in-formato-gtfs)
(ATM, CC BY 4.0) and the [Regione Lombardia railway GTFS](https://www.dati.lombardia.it/d/3z4k-mxz9)
(Trenord, S lines). A GitHub Action rebuilds `data/<profile>.json` every night
and whenever `trips.json` changes; the app downloads them from this repo.

## Files

- `atm_trip.star` – the app. Upload it once to the Tronbyt server and install
  it once per profile.
- `trips.json` – the profiles. Each one is a list of legs.
- `tools/build_timetable.py` – GTFS + `trips.json` → `data/<profile>.json`.
- `.github/workflows/timetable.yml` – nightly rebuild.

## Changing a trip

Edit `trips.json` on GitHub; the Action rebuilds the data within a minute and
the display follows within three hours (the app caches the download). Nothing
has to be re-uploaded to the Tronbyt.

A leg is:

    {
      "feed": "trenord",              atm (default) or trenord
      "route": ["S9", "S19"],         route_id(s) in routes.txt (M2, T14, B327, S9...)
      "from": ["S01032"],             stop_id(s) where you can board
      "to": ["S01065"],               stop_id(s) where you get off
      "label": "S9/S19", "color": "#a2338a",
      "from_label": "ROMOLO", "to_label": "TREZZANO"
    }

The direction is implied: only trips calling at a `to` stop after a `from`
stop are kept. Stop ids are in `stops.txt` of the feed (ATM surface stops are
numbers, ATM metro stations are names like `PIOLA`, Trenord stations are
`S0xxxx` codes). A leg with several routes shows the line of each trip.
`transfer_min` on the profile is the walking time between one leg and the next.

## App settings

- *Profilo* – profile name in `trips.json`.
- *Minuti per arrivare alla fermata* – departures leaving sooner are hidden.
- *Minuti a piedi dopo l'ultima fermata* – added to the arrival time.
- *Nome della destinazione* – replaces the last stop's name (single-leg trips).

An amber stop name means the feed has expired and the app is guessing from
the weekday.

## Development

    python3 -m unittest tools/test_build_timetable.py
    python3 tools/build_timetable.py            # downloads the feeds (~37 MB)
    python3 tools/build_timetable.py --zip atm=gtfs-atm.zip --zip trenord=gtfs-trenord.zip
    python3 -m http.server 8765 &
    pixlet render atm_trip.star profile=laura \
        timetable_url=http://127.0.0.1:8765/data/laura.json \
        now=2026-09-22T08:00:00+02:00 -m 8
