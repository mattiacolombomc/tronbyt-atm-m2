# tronbyt-atm-m2

Tronbyt / Pixlet app: minutes to the next M2 (green line) trains from
**Porta Genova** towards Piola (Gessate, Cologno Nord and Cascina Gobba
trains), plus the arrival time at Piola / Politecnico.

Times are **scheduled**, not real time: ATM does not publish live metro data.
They come from the [Comune di Milano GTFS feed](https://dati.comune.milano.it/dataset/ds929-orari-del-trasporto-pubblico-locale-nel-comune-di-milano-in-formato-gtfs)
(CC BY 4.0). A GitHub Action rebuilds `timetable.json` every night; the app
downloads it from this repo.

## Files

- `atm_m2.star` – the app. Upload it to the Tronbyt server.
- `tools/build_timetable.py` – GTFS → `timetable.json`.
- `.github/workflows/timetable.yml` – nightly rebuild.

## Settings

- *Minuti per arrivare al binario* – trains leaving sooner are hidden.
- *Minuti da Piola al Polimi* – added to the arrival time.

An amber station name means the feed has expired and the app is guessing
from the weekday.

## Development

    python3 -m unittest tools/test_build_timetable.py
    python3 tools/build_timetable.py            # downloads the feed (~35 MB)
    pixlet render atm_m2.star now=2026-09-22T08:00:00+02:00 -m 8

To use another leg of the network change `ROUTE`, `ORIGIN` and `DEST` in
`tools/build_timetable.py` (stop ids from `stops.txt`).
