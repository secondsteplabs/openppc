"""The API version each platform is called at, and the day the platform turns it off. A test fails 60 days before
one, so a release moves to a newer version in time (SCOPE_WIDENING_PLAN.md, Phase 8)."""
import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class Version:
    name: str
    sunset: dt.date | None  # None: the platform has announced no end
    source: str


GOOGLE = Version("v25", dt.date(2027, 8, 1),
                 "Google's timetable gives August 2027, a month, so the first of it; "
                 "developers.google.com/google-ads/api/docs/sunset-dates, read Oct 13, 2026")
MICROSOFT = Version("v13", None,
                    "Reporting v13 over REST: no end announced. The SOAP API ends Jan 31, 2027, and this doesn't use "
                    "it; learn.microsoft.com/advertising/guides/migrate-to-rest, read Oct 13, 2026")
META = Version("v25.0", dt.date(2028, 7, 29),
               "an estimate: Meta's changelog refused to be read here, and a tracker citing it gives July 29, 2028 "
               "for Graph API v25.0; check developers.facebook.com/docs/graph-api/changelog")

VERSIONS = {"google": GOOGLE, "microsoft": MICROSOFT, "meta": META}
WARN_DAYS = 60
