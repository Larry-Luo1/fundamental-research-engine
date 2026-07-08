from __future__ import annotations

import unittest

from fundamental_research_engine.cninfo import (
    _ms_to_date,
    _parse_announcement,
    _strip_em,
    announcement_to_evidence,
    search_announcements,
)

# Shape mirrors a real cninfo hisAnnouncement/query hit (verified against
# www.cninfo.com.cn on 2026-07-08).
_ANN = {
    "secCode": "002340",
    "secName": "格林美",
    "announcementTitle": "关于签署共建<em>固态</em><em>电池</em>正极材料联合实验室的公告",
    "announcementTime": 1780675200000,  # Beijing 2026-06-06 midnight
    "adjunctUrl": "finalpage/2026-06-06/1225355187.PDF",
    "orgId": "9900012345",
    "announcementId": "1225355187",
}


def _payload(anns):
    return {"announcements": anns, "totalAnnouncement": len(anns)}


class ParseAnnouncementTest(unittest.TestCase):
    def test_parses_all_fields_and_builds_url(self) -> None:
        hit = _parse_announcement(_ANN)
        self.assertEqual(hit["code"], "002340")
        self.assertEqual(hit["name"], "格林美")
        self.assertEqual(hit["headline"], "关于签署共建固态电池正极材料联合实验室的公告")
        self.assertEqual(hit["date"], "2026-06-06")
        self.assertEqual(hit["url"], "http://static.cninfo.com.cn/finalpage/2026-06-06/1225355187.PDF")
        self.assertEqual(hit["title"], "格林美(002340) 关于签署共建固态电池正极材料联合实验室的公告")

    def test_missing_fields_are_tolerated(self) -> None:
        hit = _parse_announcement({})
        self.assertEqual(hit["url"], "")
        self.assertEqual(hit["date"], "")
        self.assertEqual(hit["title"], "")

    def test_strip_em_and_bad_timestamp(self) -> None:
        self.assertEqual(_strip_em("a<em>b</em>c"), "abc")
        self.assertEqual(_ms_to_date(None), "")
        self.assertEqual(_ms_to_date("not-a-number"), "")


class SearchAnnouncementsTest(unittest.TestCase):
    def test_respects_limit(self) -> None:
        payload = _payload([_ANN, _ANN, _ANN])
        hits = search_announcements("固态电池", limit=2, http_post=lambda url, data: payload)
        self.assertEqual(len(hits), 2)

    def test_stops_when_page_not_full(self) -> None:
        calls = []

        def fake(url, data):
            calls.append(data["pageNum"])
            return _payload([_ANN])  # 1 < page size -> stop after one page

        hits = search_announcements("HBM", limit=10, http_post=fake)
        self.assertEqual(len(hits), 1)
        self.assertEqual(calls, ["1"])

    def test_date_range_only_applied_when_both_present(self) -> None:
        seen = {}

        def fake(url, data):
            seen.update(data)
            return _payload([])

        search_announcements("x", date_from="2026-01-01", http_post=fake)
        self.assertEqual(seen["seDate"], "")
        search_announcements("x", date_from="2026-01-01", date_to="2026-06-30", http_post=fake)
        self.assertEqual(seen["seDate"], "2026-01-01~2026-06-30")


class AnnouncementToEvidenceTest(unittest.TestCase):
    def test_evidence_shape(self) -> None:
        ev = announcement_to_evidence(_parse_announcement(_ANN), evidence_id="S1")
        self.assertEqual(ev["id"], "S1")
        self.assertEqual(ev["source_type"], "regulatory_filing")
        self.assertEqual(ev["reliability"], "high")
        self.assertEqual(ev["date"], "2026-06-06")
        self.assertEqual(ev["url"], "http://static.cninfo.com.cn/finalpage/2026-06-06/1225355187.PDF")
        self.assertEqual(ev["claims"], [])


if __name__ == "__main__":
    unittest.main()
