import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from performance import PerformanceLog
from filter_engine import parse_materials


class PerformanceTests(unittest.TestCase):
    def test_perf_csv_has_all_stage_rows_and_total(self):
        messages = []
        timing = PerformanceLog(messages.append)
        with timing.stage('material selection'):
            pass
        with timing.stage('export'):
            pass
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'check.timing.csv'
            timing.save(target)
            with target.open(encoding='utf-8-sig', newline='') as f:
                records = list(csv.DictReader(f))
        self.assertEqual([row['stage'] for row in records],
                         ['material selection', 'export', 'TOTAL elapsed'])
        self.assertTrue(all(float(row['duration_seconds']) >= 0 for row in records))

    def test_material_lists_preserve_existing_or_semantics(self):
        self.assertEqual(parse_materials('Stahlbeton Schweiz;Beton C30/37\nSTAHLBETON SCHWEIZ'),
                         ['Stahlbeton Schweiz', 'Beton C30/37', 'STAHLBETON SCHWEIZ'])


if __name__ == '__main__':
    unittest.main()
