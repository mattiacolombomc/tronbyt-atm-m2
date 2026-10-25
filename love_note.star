"""
Applet: Love Note
Summary: A short message until a time
Description: Shows a two-line message with a beating heart until the given date and time, then renders nothing (so an autopinned install unpins itself).
Author: mattiacolombomc
"""

load("render.star", "render")
load("schema.star", "schema")
load("time.star", "time")

TIMEZONE = "Europe/Rome"
PINK = "#ff2d75"
DARK_PINK = "#b0144d"
WHITE = "#ffffff"

HEART = [
    ".XX.XX.",
    "XXXXXXX",
    "XXXXXXX",
    ".XXXXX.",
    "..XXX..",
    "...X...",
]

def heart(color):
    return render.Column(children = [
        render.Row(children = [
            render.Box(width = 1, height = 1, color = color) if c == "X" else render.Box(width = 1, height = 1)
            for c in row.elems()
        ])
        for row in HEART
    ])

def beating_heart():
    return render.Animation(children = [heart(PINK)] * 6 + [heart(DARK_PINK)] * 2 + [heart(PINK)] * 2 + [heart(DARK_PINK)] * 2)

def main(config):
    until = config.get("until") or ""
    if until:
        expiry = time.parse_time(until, format = "2006-01-02 15:04", location = TIMEZONE)
        if time.now() >= expiry:
            return []  # nothing to show: the server skips the app and drops the autopin

    message = config.get("message") or "MI MANCHI MINI"
    words = message.upper().split(" ")
    second = words.pop() if len(words) > 1 else ""
    first = " ".join(words)

    return render.Root(
        delay = 120,
        child = render.Column(
            expanded = True,
            main_align = "space_evenly",
            cross_align = "center",
            children = [
                render.Text(first, font = "6x13", color = WHITE),
                render.Row(
                    cross_align = "center",
                    children = [
                        beating_heart(),
                        render.Box(width = 3, height = 1),
                        render.Text(second, font = "6x13", color = PINK),
                        render.Box(width = 3, height = 1),
                        beating_heart(),
                    ],
                ),
            ],
        ),
    )

def get_schema():
    return schema.Schema(
        version = "1",
        fields = [
            schema.Text(
                id = "message",
                name = "Messaggio",
                desc = "L'ultima parola va sulla seconda riga, tra i cuori.",
                icon = "heart",
                default = "MI MANCHI MINI",
            ),
            schema.Text(
                id = "until",
                name = "Mostra fino a",
                desc = "Ora di Roma, formato AAAA-MM-GG HH:MM. Vuoto = per sempre.",
                icon = "clock",
                default = "",
            ),
        ],
    )
