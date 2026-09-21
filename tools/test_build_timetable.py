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
"""

CALENDAR_DATES = """"service_id","date","exception_type"
"wk","20260921","1"
"wk","20260922","1"
"wk","20260914","1"
"sun","20260927","1"
"unrelated","20260921","1"
"""


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "gtfs.zip")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("trips.txt", TRIPS)
            archive.writestr("stop_times.txt", STOP_TIMES)
            archive.writestr("calendar_dates.txt", CALENDAR_DATES)
        cls.timetable = build_timetable.build(path, today="20260921")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_keeps_only_eastbound_trips_reaching_dest(self):
        # west1 runs the other way, short never reaches Piola, other is M1
        self.assertEqual(
            self.timetable["services"]["wk"],
            [[7 * 3600 + 30, 0, 22 * 60 - 30], [24 * 3600 + 600, 1, 21 * 60 + 49]],
        )
        self.assertEqual(self.timetable["services"]["sun"], [[36000, 0, 21 * 60]])
        self.assertEqual(self.timetable["headsigns"], ["gessate", "cologno nord"])

    def test_days_drop_the_past_and_unrelated_services(self):
        self.assertEqual(
            self.timetable["days"],
            {"20260921": ["wk"], "20260922": ["wk"], "20260927": ["sun"]},
        )
        self.assertEqual(self.timetable["valid_until"], "20260927")

    def test_weekday_fallback(self):
        self.assertEqual(self.timetable["fallback"]["Mon"], ["wk"])
        self.assertEqual(self.timetable["fallback"]["Sun"], ["sun"])


if __name__ == "__main__":
    unittest.main()
