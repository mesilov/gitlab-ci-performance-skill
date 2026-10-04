import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts'))
from report_collect import next_page


class GitLabKeysetPaginationTests(unittest.TestCase):
    def test_accepts_project_id_repeated_in_keyset_query(self):
        endpoint = 'projects/42/jobs?cursor=opaque%3D&id=42&order_by=id&page=1&pagination=keyset&per_page=100&sort=desc'
        header = f'Link: <https://gitlab.example.com/api/v4/{endpoint}>; rel="next"'
        self.assertEqual(next_page(header, 'gitlab.example.com', 42), endpoint)

    def test_repeated_project_id_cannot_change_project_or_add_credentials(self):
        for query in ['id=43', 'id=42&id=43', 'id=42&private_token=secret', 'id=42x', 'id=']:
            with self.subTest(query=query):
                header = f'Link: <https://gitlab.example.com/api/v4/projects/42/jobs?{query}>; rel="next"'
                with self.assertRaisesRegex(ValueError, 'Unsafe pagination target'):
                    next_page(header, 'gitlab.example.com', 42)
