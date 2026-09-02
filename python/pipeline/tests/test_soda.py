import unittest

from crosswalk_pipeline.soda import fetch_soda_records


class SodaPaginationTest(unittest.TestCase):
    def test_walks_past_the_socrata_default_page_of_100(self) -> None:
        catalog = [{"unique_key": str(i)} for i in range(115)]
        calls: list[dict] = []

        def getter(_url: str, params: dict) -> list[dict]:
            calls.append(dict(params))
            offset = int(params["$offset"])
            limit = int(params["$limit"])
            return catalog[offset : offset + limit]

        rows = fetch_soda_records(
            "https://example.test/erm2-nwe9.json",
            select="unique_key",
            where="1=1",
            order="unique_key",
            page_size=100,
            getter=getter,
        )
        self.assertEqual(len(rows), 115)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["$limit"], "100")
        self.assertEqual(calls[0]["$offset"], "0")
        self.assertEqual(calls[1]["$offset"], "100")
        self.assertEqual(calls[0]["$order"], "unique_key")
