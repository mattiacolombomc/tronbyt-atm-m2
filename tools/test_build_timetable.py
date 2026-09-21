import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
import build_timetable

TRIPS = """"route_id","service_id","trip_id","trip_headsign"
"M2","wk","east1","gessate"
"M2","wk","east_night","cologno nord"
"M2","wk","west1","assago milanofiori forum"
"M2","wk","short","cascina gobba"
"M2","sun","east_sun","gessate"
"M1","wk","other","sesto"
"T14","wk","tram_main","lorenteggio"
"T14","school","tram_depot","lorenteggio"
"T14","wk","tram_back","p.ta genova m2"
"""

STOP_TIMES = """"trip_id","arrival_time","departure_time","stop_id","stop_sequence"
"east1","07:00:00","07:00:30","P.TA GENOVA F.S.","4"
"east1","07:22:00","07:22:30","PIOLA","16"
"east_night","24:10:00","24:10:00","P.TA GENOVA F.S.","4"
"east_night","24:31:49","24:31:49","PIOLA","16"
"west1","08:00:00","08:00:00","PIOLA","5"
"west1","08:22:00","08:22:00","P.TA GENOVA F.S.","17"
"short","09:00:00","09:00:00","P.TA GENOVA F.S.","4"
"east_sun","10:00:00","10:00:00","P.TA GENOVA F.S.","4"
"east_sun","10:21:00","10:21:00","PIOLA","16"
"other","07:00:00","07:00:00","P.TA GENOVA F.S.","1"
"other","07:30:00","07:30:00","PIOLA","2"
"tram_main","08:00:00","08:00:00","11182","5"
"tram_main","08:24:00","08:24:00","12984","21"
"tram_depot","07:05:00","07:05:00","11181","1"
"tram_depot","07:26:00","07:26:00","12984","17"
"tram_back","09:00:00","09:00:00","12984","1"
"tram_back","09:25:00","09:25:00","11181","17"
"""

CALENDAR_DATES = """"service_id","date","exception_type"
"wk","20260921","1"
"wk","20260922","1"
"wk","20260914","1"
"school","20260921","1"
"sun","20260927","1"
"unrelated","20260921","1"
"""

PROFILES = {
    "metro": {
        "legs": [
            {"route": "M2", "label": "M2", "from": ["P.TA GENOVA F.S."], "to": ["PIOLA"]},
        ],
    },
    "tram": {
        "transfer_min": 4,
        "legs": [
            {"route": "T14", "label": "14", "from": ["11182", "11181"], "to": ["12984"]},
            {"route": "M2", "from": ["P.TA GENOVA F.S."], "to": ["PIOLA"]},
        ],
    },
}


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "gtfs.zip")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("trips.txt", TRIPS)
            archive.writestr("stop_times.txt", STOP_TIMES)
            archive.writestr("calendar_dates.txt", CALENDAR_DATES)
        cls.timetables = build_timetable.build(path, PROFILES, today="20260921")
        cls.metro = cls.timetables["metro"]["legs"][0]
        cls.tram = cls.timetables["tram"]["legs"][0]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_keeps_only_trips_reaching_dest_after_origin(self):
        # west1 runs the other way, short never reaches Piola, other is M1
        self.assertEqual(
            self.metro["services"]["wk"],
            [[7 * 3600 + 30, 22 * 60 - 30], [24 * 3600 + 600, 21 * 60 + 49]],
        )
        self.assertEqual(self.metro["services"]["sun"], [[36000, 21 * 60]])

    def test_days_drop_the_past_and_unrelated_services(self):
        self.assertEqual(
            self.metro["days"],
            {"20260921": ["wk"], "20260922": ["wk"], "20260927": ["sun"]},
        )
        self.assertEqual(self.metro["valid_until"], "20260927")
        self.assertEqual(self.metro["fallback"]["Mon"], ["wk"])
        self.assertEqual(self.metro["fallback"]["Sun"], ["sun"])

    def test_several_boarding_stops_and_services_on_one_day(self):
        # tram_back calls at 11181 too, but after 12984: it must not be listed
        self.assertEqual(self.tram["services"], {"wk": [[28800, 1440]], "school": [[25500, 1260]]})
        self.assertEqual(self.tram["days"]["20260921"], ["school", "wk"])

    def test_profile_metadata(self):
        self.assertEqual(self.timetables["tram"]["transfer_min"], 4)
        self.assertEqual(self.tram["label"], "14")
        self.assertEqual(self.timetables["tram"]["valid_until"], "20260922")


if __name__ == "__main__":
    unittest.main()
