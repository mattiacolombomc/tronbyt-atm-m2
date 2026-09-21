#!/usr/bin/env python3
"""Build a compact timetable.json for one metro leg out of the Milan GTFS feed.

The feed (Comune di Milano / AMAT open data) is ~35 MB zipped and its
stop_times.txt is ~440 MB, far too big for a Tronbyt app to read at render
time. This script keeps only the trips of ROUTE that call at ORIGIN and,
later in the same trip, at DEST: that is what selects the direction.
"""

import argparse
import collections
import csv
import datetime
import io
import json
import sys
import urllib.request
import zipfile

CKAN_PACKAGE = (
    "https://dati.comune.milano.it/api/3/action/package_show"
    "?id=ds929-orari-del-trasporto-pubblico-locale-nel-comune-di-milano-in-formato-gtfs"
)
ROUTE = "M2"
ORIGIN = "P.TA GENOVA F.S."
DEST = "PIOLA"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CALENDAR_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def gtfs_url():
    with urllib.request.urlopen(CKAN_PACKAGE, timeout=60) as resp:
        package = json.load(resp)
    for resource in package["result"]["resources"]:
        if resource["url"].lower().endswith(".zip"):
            return resource["url"]
    raise RuntimeError("no zip resource in the CKAN package")


def download(url, path):
    with urllib.request.urlopen(url, timeout=600) as resp, open(path, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def seconds(hms):
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def text(archive, name):
    return io.TextIOWrapper(archive.open(name), encoding="utf-8-sig", newline="")


def read_trips(archive, route):
    """trip_id -> (service_id, headsign) for the trips of `route`."""
    trips = {}
    for row in csv.DictReader(text(archive, "trips.txt")):
        if row["route_id"] == route:
            trips[row["trip_id"]] = (row["service_id"], row["trip_headsign"])
    return trips


def read_calls(archive, trips, origin, dest):
    """trip_id -> {stop_id: (stop_sequence, arrival, departure)} for the two stops."""
    calls = collections.defaultdict(dict)
    lines = text(archive, "stop_times.txt")
    header = next(csv.reader([next(lines)]))
    col = {name: i for i, name in enumerate(header)}
    needles = ('"%s"' % origin, '"%s"' % dest, ",%s," % origin, ",%s," % dest)
    for line in lines:
        # cheap substring test first: parsing all ~5M rows as csv is slow
        if not any(n in line for n in needles):
            continue
        row = next(csv.reader([line]))
        trip_id, stop_id = row[col["trip_id"]], row[col["stop_id"]]
        if trip_id in trips and stop_id in (origin, dest):
            calls[trip_id][stop_id] = (
                int(row[col["stop_sequence"]]),
                seconds(row[col["arrival_time"]]),
                seconds(row[col["departure_time"]]),
            )
    return calls


def read_days(archive, service_ids):
    """date (YYYYMMDD) -> sorted list of active service ids."""
    days = collections.defaultdict(set)
    names = archive.namelist()
    if "calendar.txt" in names:
        for row in csv.DictReader(text(archive, "calendar.txt")):
            if row["service_id"] not in service_ids:
                continue
            day = datetime.datetime.strptime(row["start_date"], "%Y%m%d").date()
            end = datetime.datetime.strptime(row["end_date"], "%Y%m%d").date()
            while day <= end:
                if row[CALENDAR_COLUMNS[day.weekday()]] == "1":
                    days[day.strftime("%Y%m%d")].add(row["service_id"])
                day += datetime.timedelta(days=1)
    if "calendar_dates.txt" in names:
        for row in csv.DictReader(text(archive, "calendar_dates.txt")):
            if row["service_id"] not in service_ids:
                continue
            if row["exception_type"] == "1":
                days[row["date"]].add(row["service_id"])
            else:
                days[row["date"]].discard(row["service_id"])
    return {date: sorted(ids) for date, ids in days.items() if ids}


def weekday_fallback(days):
    """Most common service set per weekday, used for dates the feed does not list."""
    votes = collections.defaultdict(collections.Counter)
    for date, ids in days.items():
        weekday = datetime.datetime.strptime(date, "%Y%m%d").weekday()
        votes[WEEKDAYS[weekday]][tuple(ids)] += 1
    return {day: list(counter.most_common(1)[0][0]) for day, counter in votes.items()}


def build(zip_path, route=ROUTE, origin=ORIGIN, dest=DEST, today=None):
    with zipfile.ZipFile(zip_path) as archive:
        trips = read_trips(archive, route)
        calls = read_calls(archive, trips, origin, dest)

        services = collections.defaultdict(list)
        headsigns = []
        for trip_id, stops in calls.items():
            if origin not in stops or dest not in stops:
                continue
            if stops[dest][0] <= stops[origin][0]:
                continue  # opposite direction
            service_id, headsign = trips[trip_id]
            if headsign not in headsigns:
                headsigns.append(headsign)
            departure = stops[origin][2]
            services[service_id].append(
                [departure, headsigns.index(headsign), stops[dest][1] - departure]
            )
        if not services:
            raise RuntimeError("no %s trips from %r to %r in the feed" % (route, origin, dest))
        for departures in services.values():
            departures.sort()

        days = read_days(archive, set(services))

    today = today or datetime.date.today().strftime("%Y%m%d")
    # past days are dead weight, but keep yesterday: its after-midnight trips run today
    yesterday = (
        datetime.datetime.strptime(today, "%Y%m%d") - datetime.timedelta(days=1)
    ).strftime("%Y%m%d")
    fallback = weekday_fallback(days)
    return {
        "generated": today,
        "route": route,
        "origin": origin,
        "dest": dest,
        "valid_until": max(days) if days else today,
        "headsigns": headsigns,
        "days": {date: ids for date, ids in sorted(days.items()) if date >= yesterday},
        "fallback": fallback,
        "services": dict(services),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zip", help="use this GTFS zip instead of downloading the feed")
    parser.add_argument("--out", default="timetable.json")
    args = parser.parse_args()

    zip_path = args.zip
    if not zip_path:
        zip_path = "gtfs.zip"
        url = gtfs_url()
        print("downloading", url, file=sys.stderr)
        download(url, zip_path)

    timetable = build(zip_path)
    with open(args.out, "w") as out:
        json.dump(timetable, out, separators=(",", ":"))
        out.write("\n")
    print(
        "%s: %d services, %d departures, valid until %s"
        % (
            args.out,
            len(timetable["services"]),
            sum(len(d) for d in timetable["services"].values()),
            timetable["valid_until"],
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
