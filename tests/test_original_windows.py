"""Canonical history pages retain every attempt independently of the baseline."""
import copy
import sys
import unittest
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/gitlab-ci-performance/scripts'))
from fixture_v2 import sample
from report_calculate import build_report
from report_contract import validate
from report_export import export_report

AT = '2026-10-04T00:00:00Z'


class OriginalWindowsTests(unittest.TestCase):
    def report(self, count):
        return build_report(sample(count), generated_at=AT)

    def test_every_16_and_32_page_has_ordered_members_and_adjacent_links(self):
        for count in (0, 1, 16, 17, 32, 33, 64):
            with self.subTest(count=count):
                report = self.report(count)
                expected = [(size, page) for size in (16, 32)
                            for page in range((count + size - 1) // size)]
                self.assertEqual([(w['size'], w['page']) for w in report['windows']], expected)
                if not count:
                    self.assertEqual(report['job_types'], [])
                    continue
                typ = report['job_types'][0]
                self.assertEqual(typ['window_ids'], [w['id'] for w in report['windows']])
                self.assertEqual(typ['retained_attempt_ids'], list(range(count, 0, -1)))
                self.assertEqual(typ['baseline']['maximum'], 10)
                self.assertEqual(typ['baseline']['attempt_ids'], list(range(count - 1, max(count - 11, 0), -1)))
                for size in (16, 32):
                    pages = [w for w in report['windows'] if w['size'] == size]
                    flattened = [aid for w in pages for aid in w['attempt_ids']]
                    self.assertEqual(flattened, list(range(count, 0, -1)))
                    self.assertEqual(len(flattened), len(set(flattened)))
                    for page, window in enumerate(pages):
                        ids = list(range(count, 0, -1))[page * size:(page + 1) * size]
                        self.assertEqual(window['attempt_ids'], ids)
                        self.assertEqual(window['anchor_attempt_id'], ids[0])
                        for direction, neighbor in (('older', page + 1), ('newer', page - 1)):
                            present = 0 <= neighbor < len(pages)
                            self.assertEqual(window['has_' + direction], present)
                            self.assertEqual(window[direction + '_window_id'], pages[neighbor]['id'] if present else None)

    def test_each_page_statistics_use_its_members_and_baseline_stays_independent(self):
        source = sample(64)
        for job in source['jobs']:
            job['duration_seconds'] = job['id'] * 10
            if job['id'] % 5 == 0:
                job['status'] = 'failed'
        report = build_report(source, generated_at=AT)
        typ = report['job_types'][0]
        expected_baseline = [i for i in range(63, 0, -1) if i % 5][:10]
        self.assertEqual(typ['baseline']['attempt_ids'], expected_baseline)
        for window in report['windows']:
            eligible = [i for i in window['attempt_ids'] if i % 5]
            self.assertEqual(window['descriptive']['attempt_ids'], eligible)
            self.assertEqual(window['inferential']['attempt_ids'], eligible)
            self.assertEqual(window['findings']['eligible_successful_n'], len(eligible))
            self.assertEqual(window['findings']['metrics'], window['inferential']['metrics'])
            self.assertEqual(window['findings']['metrics']['execution']['known'], len(eligible))
            self.assertEqual(window['findings']['metrics']['execution']['median_seconds'], median(i * 10 for i in eligible))
        self.assertNotEqual(report['windows'][0]['inferential']['metrics'], report['windows'][1]['inferential']['metrics'])

    def test_all_older_pages_export_with_canonical_navigation(self):
        report = self.report(64)
        for window in report['windows']:
            compact = export_report(report, window_id=window['id'])
            self.assertEqual(compact['windows'], [window])
            validate(compact, 'compact')

    def test_contract_rejects_missing_duplicate_and_misdirected_pages(self):
        report = self.report(64)
        def remove_page_and_repair_pointers(changed):
            removed = changed['windows'].pop()
            changed['job_types'][0]['window_ids'].remove(removed['id'])
            changed['windows'][-1].update(older_window_id=None, has_older=False)
        mutations = {
            'missing page': lambda r: r['windows'].pop(),
            'missing page with repaired pointers': remove_page_and_repair_pointers,
            'duplicate page': lambda r: r['windows'][1].update(page=0),
            'non-adjacent link': lambda r: r['windows'][0].update(older_window_id=r['windows'][2]['id']),
            'cross-size link': lambda r: r['windows'][0].update(older_window_id=r['windows'][-1]['id']),
            'missing link': lambda r: r['windows'][0].update(older_window_id=None, has_older=False),
            'reversed link': lambda r: r['windows'][1].update(older_window_id=r['windows'][0]['id']),
            'duplicate type pointer': lambda r: r['job_types'][0]['window_ids'].append(r['windows'][0]['id']),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(report)
                mutate(changed)
                with self.assertRaises(ValueError):
                    validate(changed, 'report')


if __name__ == '__main__':
    unittest.main()
