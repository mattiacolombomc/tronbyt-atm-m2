"""
Applet: ATM Trip
Summary: Next ATM Milano departures
Description: Minutes to the next departures of a commute in Milan (ATM metro, tram, bus and Trenord suburban trains), with connection and arrival time. Scheduled times from the Comune di Milano and Regione Lombardia GTFS feeds, rebuilt every night.
Author: mattiacolombomc
"""

load("cache.star", "cache")
load("encoding/json.star", "json")
load("http.star", "http")
load("render.star", "render")
load("schema.star", "schema")
load("time.star", "time")

DATA_URL = "https://raw.githubusercontent.com/mattiacolombomc/tronbyt-atm-m2/main/data/"
TIMEZONE = "Europe/Rome"
FETCH_TTL = 3 * 3600
LAST_GOOD_TTL = 14 * 24 * 3600
DAY = 86400
VIAGGIATRENO_URL = "http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/partenze/"
DELAYS_TTL = 30  # seconds; the server renders about once a minute

WHITE = "#ffffff"
GREY = "#8a8a8a"
AMBER = "#ffb000"
RED = "#ff3030"

def get_timetable(url):
    body = None
    resp = http.get(url, ttl_seconds = FETCH_TTL)
    if resp.status_code == 200:
        body = resp.body()
        cache.set("last_good " + url, body, ttl_seconds = LAST_GOOD_TTL)
    else:
        # GitHub unreachable: a timetable from a few days ago is still right
        body = cache.get("last_good " + url)
    if not body:
        return None
    return json.decode(body)

def url_encode(text):
    return text.replace("%", "%25").replace(" ", "%20").replace(":", "%3A").replace("+", "%2B")

def delays(leg, now, override_url):
    """train number -> delay in seconds, from the station's live departure board."""
    source = leg.get("realtime")
    if not source or "viaggiatreno" not in source:
        return {}

    # ViaggiaTreno wants the current time in the path, in JavaScript's Date format
    stamp = now.format("Mon Jan 02 2006 15:04:05 GMT-0700")
    url = override_url or VIAGGIATRENO_URL + source["viaggiatreno"] + "/" + url_encode(stamp)
    resp = http.get(url, ttl_seconds = DELAYS_TTL)
    if resp.status_code != 200:
        return {}
    found = {}
    for train in resp.json():
        # numbers come back as floats
        number, delay = train.get("numeroTreno"), train.get("ritardo")
        if type(number) in ("int", "float") and type(delay) in ("int", "float"):
            # an early train still leaves at the scheduled time
            found[int(number)] = max(int(delay), 0) * 60
    return found

def services_on(leg, day):
    ids = leg["days"].get(day.format("20060102"))
    if ids == None:
        ids = leg["fallback"].get(day.format("Mon"), [])
    return ids

def upcoming(leg, now, earliest, late = {}):
    """(departure, arrival, line, delay) tuples leaving not before `earliest`.

    Times are seconds from today's midnight and already include the delay,
    which `late` gives per train number (0 for anything not on the board)."""
    found = []

    # yesterday's service day runs past midnight (GTFS times like 24:37:27)
    for day, offset in [(now - time.parse_duration("24h"), -DAY), (now, 0)]:
        for service in services_on(leg, day):
            for row in leg["services"].get(service, []):
                delay = late.get(row[3], 0) if len(row) > 3 else 0
                at = row[0] + offset + delay
                if at >= earliest:
                    found.append((at, at + row[1], leg["lines"][row[2]], delay))
    return sorted(found)

def two_digits(n):
    return ("0" if n < 10 else "") + str(n)

def clock(seconds):
    seconds = seconds % DAY
    return two_digits(seconds // 3600) + ":" + two_digits((seconds % 3600) // 60)

def int_config(config, key):
    value = config.get(key) or "0"
    return int(value) if value.isdigit() else 0

def badge(leg):
    label = leg.get("label", "?")
    return render.Box(
        width = len(label) * 4 + 3,
        height = 7,
        color = leg.get("color", WHITE),
        child = render.Padding(
            pad = (1, 1, 0, 0),
            child = render.Text(label, font = "tom-thumb", color = "#000000"),
        ),
    )

def header(leg, stale):
    return render.Row(
        cross_align = "center",
        children = [
            badge(leg),
            render.Box(width = 2, height = 1),
            render.Text(leg.get("from_label", ""), font = "tom-thumb", color = AMBER if stale else WHITE),
        ],
    )

def page(top, rows):
    return render.Root(
        child = render.Column(
            expanded = True,
            main_align = "space_between",
            children = [top] + rows,
        ),
    )

def lines(texts):
    return [render.Text(text, font = "tom-thumb", color = color) for text, color in texts]

def main(config):
    now = time.now().in_location(TIMEZONE)
    if config.get("now"):
        now = time.parse_time(config.get("now")).in_location(TIMEZONE)

    profile = (config.get("profile") or "mattia").strip().lower()
    timetable = get_timetable(config.get("timetable_url") or DATA_URL + profile + ".json")
    if timetable == None:
        title = render.Text(profile.upper(), font = "tom-thumb", color = WHITE)
        return page(title, lines([("ORARIO NON", RED), ("DISPONIBILE", RED)]))

    legs = timetable["legs"]
    color = legs[0].get("color", WHITE)
    top = header(legs[0], now.format("20060102") > timetable["valid_until"])
    transfer = timetable.get("transfer_min", 0) * 60
    second = now.hour * 3600 + now.minute * 60 + now.second

    realtime_url = config.get("realtime_url")
    trains = upcoming(legs[0], now, second + int_config(config, "walk") * 60, delays(legs[0], now, realtime_url))
    if not trains:
        return page(top, lines([("NESSUNA CORSA", RED)]))
    first, arrival, _, first_delay = trains[0]

    # ride the first departure through the following legs
    connection = None
    for leg in legs[1:]:
        onward = upcoming(leg, now, arrival + transfer, delays(leg, now, realtime_url))
        if not onward:
            return page(top, lines([("NESSUNA", RED), ("COINCIDENZA " + leg.get("label", ""), RED)]))
        connection = (leg, onward[0][0], onward[0][2], onward[0][3])
        arrival = onward[0][1]
    arrival += int_config(config, "after") * 60

    if connection:
        leg, leaves, line, delay = connection

        # times already include the delay; the colour says it is not the timetable
        delay_color = RED if delay >= 600 else AMBER if delay > 0 else None
        bottom = render.Row(
            children = [
                render.Text(line, font = "tom-thumb", color = leg.get("color", WHITE)),
                render.Text(" " + clock(leaves), font = "tom-thumb", color = delay_color or WHITE),
                render.Text(">" + clock(arrival), font = "tom-thumb", color = delay_color or GREY),
            ],
        )
    else:
        label = config.get("arrival_label") or legs[0].get("to_label", "")
        bottom = render.Text(label + " " + clock(arrival), font = "tb-8", color = WHITE)

    wait = (first - second) // 60

    # the countdown already includes the delay; say so with the colour
    wait_color = RED if first_delay >= 600 else AMBER if first_delay > 0 else color
    if wait >= 60:
        return page(top, lines([("PRIMA CORSA", GREY), ("PARTE " + clock(first), color)]) + [bottom])

    following = " ".join([
        "%d'" % ((at - second) // 60)
        for at, _, _, _ in trains[1:3]
        if at - second < 3600
    ])
    return page(top, [
        render.Row(
            cross_align = "end",
            children = [
                render.Text("%d" % wait, font = "6x13", color = wait_color),
                render.Text("min", font = "tom-thumb", color = wait_color),
                render.Box(width = 4, height = 1),
                render.Text(following, font = "tb-8", color = GREY),
            ],
        ),
        bottom,
    ])

def get_schema():
    return schema.Schema(
        version = "1",
        fields = [
            schema.Text(
                id = "profile",
                name = "Profilo",
                desc = "Nome del percorso in trips.json (mattia, laura, laura_treno).",
                icon = "user",
                default = "mattia",
            ),
            schema.Text(
                id = "walk",
                name = "Minuti per arrivare alla fermata",
                desc = "Le corse che partono prima non vengono mostrate.",
                icon = "personWalking",
                default = "0",
            ),
            schema.Text(
                id = "after",
                name = "Minuti a piedi dopo l'ultima fermata",
                desc = "Sommati all'orario di arrivo.",
                icon = "flagCheckered",
                default = "0",
            ),
            schema.Text(
                id = "arrival_label",
                name = "Nome della destinazione",
                desc = "Vuoto = nome dell'ultima fermata.",
                icon = "tag",
                default = "",
            ),
        ],
    )
