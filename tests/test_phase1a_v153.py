"""Phase 1A safety regression tests requiring no native IFC library."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from filter_engine import ensure_unique_element_globalids, assess_selection
from performance import PerformanceLog

class InputSafetyTests(unittest.TestCase):
    def test_rejects_duplicate_element_global_ids(self):
        objects = [Mock(GlobalId='A'*22), Mock(GlobalId='A'*22)]
        with self.assertRaisesRegex(ValueError, 'Duplicate IfcElement.GlobalId'):
            ensure_unique_element_globalids(objects)

    def test_accepts_unique_element_global_ids(self):
        ensure_unique_element_globalids([Mock(GlobalId='A'*22), Mock(GlobalId='B'*22)])

    def test_empty_material_selection_aborts_and_suggests_name(self):
        with self.assertRaisesRegex(ValueError, 'Similar material names.*Stahlbeton Schweiz'):
            assess_selection(set(), [], ['Stahlbeton Schweitz'], ['Stahlbeton Schweiz'])

    def test_empty_material_selection_aborts_even_if_no_known_names(self):
        with self.assertRaisesRegex(ValueError, 'No IFC elements match'):
            assess_selection(set(), [], ['No material'], [])

    def test_partial_material_selection_warns_and_continues(self):
        log = []
        unmatched = assess_selection({12}, [{'matched_materials':'Concrete'}],
                                     ['Concrete','Steel'],['Concrete','Steel'],log.append)
        self.assertEqual(unmatched, ['Steel'])
        self.assertIn('Steel', log[0])

    def test_case_insensitive_name_match(self):
        log = []
        self.assertEqual(assess_selection({1},[{'matched_materials':'Concrete'}],
                                          ['CONCRETE'],[],log.append), [])
        self.assertFalse(log)

    def test_sampler_explicit_stop_is_idempotent(self):
        perf = PerformanceLog(lambda message: None)
        try:
            perf.stop_sampling()
            perf.stop_sampling()
            self.assertTrue(perf._stop.is_set())
            if perf._sample_thread:
                self.assertFalse(perf._sample_thread.is_alive())
        finally:
            perf.stop_sampling()
