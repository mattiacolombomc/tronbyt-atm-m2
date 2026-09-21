#!/usr/bin/env python3
"""Build compact per-profile timetables out of the Milan GTFS feed.

The feed (Comune di Milano / AMAT open data) is ~35 MB zipped and its
stop_times.txt is ~440 MB, far too big for a Tronbyt app to read at render
time. trips.json describes each profile as a list of legs (route, boarding
stops, alighting stops); for every leg this script keeps only the trips that
call at a boarding stop and, later in the same trip, at an alighting stop:
that is what selects the direction.
"""

import argparse
import collections
import csv
import datetime
import io
import json
import os
import sys
import urllib.request
import zipfile

CKAN_PACKAGE = (
    "https://dati.comune.milano.it/api/3/action/package_show"
    "?id=ds929-orari-del-trasporto-pubblico-locale-nel-comune-di-milano-in-formato-gtfs"
)
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CALENDAR_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# leg fields copied verbatim into the output for the app to display
DISPLAY_FIELDS = ["label", "color", "from_label", "to_label"]


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


def read_trips(archive, routes):
    """trip_id -> (route_id, service_id) for the trips of `routes`."""
    trips = {}
    for row in csv.DictReader(text(archive, "trips.txt")):
        if row["route_id"] in routes:
            trips[row["trip_id"]] = (row["route_id"], row["service_id"])
    return trips


def read_calls(archive, trips, stop_ids):
    """trip_id -> {stop_id: (stop_sequence, arrival, departure)} at `stop_ids`."""
    calls = collections.defaultdict(dict)
    lines = text(archive, "stop_times.txt")
    header = next(csv.reader([next(lines)]))
    col = {name: i for i, name in enumerate(header)}
    needles = ['"%s"' % s for s in stop_ids] + [",%s," % s for s in stop_ids]
    for line in lines:
        # cheap substring test first: parsing all ~5M rows as csv is slow
        if not any(n in line for n in needles):
            continue
        row = next(csv.reader([line]))
        trip_id, stop_id = row[col["trip_id"]], row[col["stop_id"]]
        if trip_id in trips and stop_id in stop_ids:
            calls[trip_id][stop_id] = (
                int(row[col["stop_sequence"]]),
                seconds(row[col["arrival_time"]]),
                seconds(row[col["departure_time"]]),
            )
    return calls


def read_calendar(archive):
    """service_id -> set of dates (YYYYMMDD) it runs on."""
    dates = collections.defaultdict(set)
    names = archive.namelist()
    if "calendar.txt" in names:
        for row in csv.DictReader(text(archive, "calendar.txt")):
            day = datetime.datetime.strptime(row["start_date"], "%Y%m%d").date()
            end = datetime.datetime.strptime(row["end_date"], "%Y%m%d").date()
            while day <= end:
                if row[CALENDAR_COLUMNS[day.weekday()]] == "1":
                    dates[row["service_id"]].add(day.strftime("%Y%m%d"))
                day += datetime.timedelta(days=1)
    if "calendar_dates.txt" in names:
        for row in csv.DictReader(text(archive, "calendar_dates.txt")):
            if row["exception_type"] == "1":
                dates[row["service_id"]].add(row["date"])
            else:
                dates[row["service_id"]].discard(row["date"])
    return dates


def weekday_fallback(days):
    """Most common service set per weekday, used for dates the feed does not list."""
    votes = collections.defaultdict(collections.Counter)
    for date, ids in days.items():
        weekday = datetime.datetime.strptime(date, "%Y%m%d").weekday()
        votes[WEEKDAYS[weekday]][tuple(ids)] += 1
    return {day: list(counter.most_common(1)[0][0]) for day, counter in votes.items()}


def build_leg(leg, trips, calls, calendar, yesterday):
    origins, dests = leg["from"], leg["to"]
    services = collections.defaultdict(list)
    for trip_id, stops in calls.items():
        route_id, service_id = trips[trip_id]
        if route_id != leg["route"]:
            continue
        boarded = [stops[s] for s in origins if s in stops]
        if not boarded:
            continue
        sequence, _, departure = min(boarded)
        # first alighting stop after boarding; none means the opposite direction
        alighted = [stops[s] for s in dests if s in stops and stops[s][0] > sequence]
        if not alighted:
            continue
        services[service_id].append([departure, min(alighted)[1] - departure])
    if not services:
        raise RuntimeError(
            "no %s trips from %r to %r in the feed" % (leg["route"], origins, dests)
        )
    for departures in services.values():
        departures.sort()

    days = collections.defaultdict(list)
    for service_id in sorted(services):
        for date in calendar.get(service_id, ()):
            days[date].append(service_id)

    out = {field: leg[field] for field in DISPLAY_FIELDS if field in leg}
    out["valid_until"] = max(days) if days else yesterday
    out["fallback"] = weekday_fallback(days)
    # past days are dead weight, but keep yesterday: its after-midnight trips run today
    out["days"] = {date: ids for date, ids in sorted(days.items()) if date >= yesterday}
    live = {s for ids in list(out["days"].values()) + list(out["fallback"].values()) for s in ids}
    out["services"] = {s: departures for s, departures in services.items() if s in live}
    return out


def build(zip_path, profiles, today=None):
    """profile name -> timetable dict."""
    today = today or datetime.date.today().strftime("%Y%m%d")
    yesterday = (
        datetime.datetime.strptime(today, "%Y%m%d") - datetime.timedelta(days=1)
    ).strftime("%Y%m%d")

    legs = [leg for profile in profiles.values() for leg in profile["legs"]]
    stop_ids = {stop for leg in legs for stop in leg["from"] + leg["to"]}
    with zipfile.ZipFile(zip_path) as archive:
        trips = read_trips(archive, {leg["route"] for leg in legs})
        calls = read_calls(archive, trips, stop_ids)
        calendar = read_calendar(archive)

    timetables = {}
    for name, profile in profiles.items():
        built = [build_leg(leg, trips, calls, calendar, yesterday) for leg in profile["legs"]]
        timetables[name] = {
            "generated": today,
            "valid_until": min(leg["valid_until"] for leg in built),
            "transfer_min": profile.get("transfer_min", 0),
            "legs": built,
        }
    return timetables


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zip", help="use this GTFS zip instead of downloading the feed")
    parser.add_argument("--trips", default="trips.json")
    parser.add_argument("--out", default="data", help="output directory")
    args = parser.parse_args()

    with open(args.trips) as f:
        profiles = json.load(f)

    zip_path = args.zip
    if not zip_path:
        zip_path = "gtfs.zip"
        url = gtfs_url()
        print("downloading", url, file=sys.stderr)
        download(url, zip_path)

    os.makedirs(args.out, exist_ok=True)
    for name, timetable in build(zip_path, profiles).items():
        path = os.path.join(args.out, name + ".json")
        with open(path, "w") as out:
            json.dump(timetable, out, separators=(",", ":"))
            out.write("\n")
        print(
            "%s: %s, valid until %s"
            % (
                path,
                ", ".join(
                    "%s %d departures" % (leg.get("label", "?"), sum(map(len, leg["services"].values())))
                    for leg in timetable["legs"]
                ),
                timetable["valid_until"],
            ),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
