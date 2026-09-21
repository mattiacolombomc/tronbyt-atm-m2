"""
Applet: ATM M2
Summary: Next M2 from P.ta Genova
Description: Minutes to the next M2 (green line) trains from Porta Genova towards Piola, with the arrival time. Scheduled times from the Comune di Milano GTFS feed, rebuilt every night.
Author: mattiacolombomc
"""

load("cache.star", "cache")
load("encoding/json.star", "json")
load("http.star", "http")
load("render.star", "render")
load("schema.star", "schema")
load("time.star", "time")

TIMETABLE_URL = "https://raw.githubusercontent.com/mattiacolombomc/tronbyt-atm-m2/main/timetable.json"
TIMEZONE = "Europe/Rome"
FETCH_TTL = 3 * 3600
LAST_GOOD_TTL = 14 * 24 * 3600
DAY = 86400

GREEN = "#5fd700"
WHITE = "#ffffff"
GREY = "#8a8a8a"
AMBER = "#ffb000"
RED = "#ff3030"

def get_timetable(url):
    body = None
    resp = http.get(url, ttl_seconds = FETCH_TTL)
    if resp.status_code == 200:
        body = resp.body()
        cache.set("last_good", body, ttl_seconds = LAST_GOOD_TTL)
    else:
        # GitHub unreachable: a timetable from a few days ago is still right
        body = cache.get("last_good")
    if not body:
        return None
    return json.decode(body)

def services_on(timetable, day):
    ids = timetable["days"].get(day.format("20060102"))
    if ids == None:
        ids = timetable["fallback"].get(day.format("Mon"), [])
    return ids

def upcoming(timetable, now, earliest):
    """Departures (seconds from today's midnight, seconds to DEST) not before `earliest`."""
    found = []

    # yesterday's service day runs past midnight (GTFS times like 24:37:27)
    for day, offset in [(now - time.parse_duration("24h"), -DAY), (now, 0)]:
        for service in services_on(timetable, day):
            for departure in timetable["services"].get(service, []):
                at = departure[0] + offset
                if at >= earliest:
                    found.append((at, departure[2]))
    return sorted(found)

def two_digits(n):
    return ("0" if n < 10 else "") + str(n)

def clock(seconds):
    seconds = seconds % DAY
    return two_digits(seconds // 3600) + ":" + two_digits((seconds % 3600) // 60)

def int_config(config, key):
    value = config.get(key) or "0"
    return int(value) if value.isdigit() else 0

def header(stale):
    return render.Row(
        cross_align = "center",
        children = [
            render.Box(
                width = 11,
                height = 7,
                color = GREEN,
                child = render.Padding(
                    pad = (1, 1, 0, 0),
                    child = render.Text("M2", font = "tom-thumb", color = "#000000"),
                ),
            ),
            render.Box(width = 2, height = 1),
            render.Text("P.TA GENOVA", font = "tom-thumb", color = AMBER if stale else WHITE),
        ],
    )

def message(stale, lines):
    return render.Root(
        child = render.Column(
            expanded = True,
            main_align = "space_between",
            children = [header(stale)] + [
                render.Text(text, font = "tom-thumb", color = color)
                for text, color in lines
            ],
        ),
    )

def main(config):
    now = time.now().in_location(TIMEZONE)
    if config.get("now"):
        now = time.parse_time(config.get("now")).in_location(TIMEZONE)

    timetable = get_timetable(config.get("timetable_url") or TIMETABLE_URL)
    if timetable == None:
        return message(False, [("ORARIO NON", RED), ("DISPONIBILE", RED)])

    stale = now.format("20060102") > timetable["valid_until"]
    walk = int_config(config, "walk") * 60
    after = int_config(config, "after") * 60

    second = now.hour * 3600 + now.minute * 60 + now.second
    trains = upcoming(timetable, now, second + walk)
    if not trains:
        return message(stale, [("NESSUNA CORSA", RED)])

    first, ride = trains[0]
    arrival = ("POLIMI " if after else "PIOLA ") + clock(first + ride + after)
    wait = (first - second) // 60
    if wait >= 60:
        return message(stale, [("PRIMA CORSA", GREY), ("PARTE " + clock(first), GREEN), (arrival, WHITE)])

    following = " ".join([
        "%d'" % ((at - second) // 60)
        for at, _ in trains[1:3]
        if at - second < 3600
    ])
    return render.Root(
        child = render.Column(
            expanded = True,
            main_align = "space_between",
            children = [
                header(stale),
                render.Row(
                    cross_align = "end",
                    children = [
                        render.Text("%d" % wait, font = "6x13", color = GREEN),
                        render.Text("min", font = "tom-thumb", color = GREEN),
                        render.Box(width = 4, height = 1),
                        render.Text(following, font = "tb-8", color = GREY),
                    ],
                ),
                render.Text(arrival, font = "tb-8", color = WHITE),
            ],
        ),
    )

def get_schema():
    return schema.Schema(
        version = "1",
        fields = [
            schema.Text(
                id = "walk",
                name = "Minuti per arrivare al binario",
                desc = "I treni che partono prima non vengono mostrati.",
                icon = "personWalking",
                default = "0",
            ),
            schema.Text(
                id = "after",
                name = "Minuti da Piola al Polimi",
                desc = "Sommati all'orario di arrivo (0 = arrivo a Piola).",
                icon = "buildingColumns",
                default = "0",
            ),
        ],
    )
