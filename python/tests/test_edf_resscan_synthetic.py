"""Focused stdlib tests for the synthetic Air11 fixed-pressure export."""
import importlib.util
from pathlib import Path
import struct
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "edf_resscan.py"
spec = importlib.util.spec_from_file_location("edf_resscan", SCRIPT)
edf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edf)


def fields_for(labels, samples, pmin=0, pmax=100, dmin=0, dmax=1000):
    columns = [
        (label, "", "", str(pmin), str(pmax), str(dmin), str(dmax), "", str(n), "")
        for label, n in zip(labels, samples)
    ]
    return [[column[row].encode("ascii").ljust(width)
             for column in columns]
            for row, width in enumerate(edf.SIGNAL_FIELD_WIDTHS)]


def record_for(values):
    return struct.pack("<" + "H" * len(values), *values)


class SyntheticPressureTests(unittest.TestCase):
    def test_missing_samples_preserved_in_detailed_pressure(self):
        fields = fields_for(["Press.40ms"], [3])
        result = edf.set_signal_constant(record_for([12, 0xffff, 40]), fields,
                                         "Press.40ms", 7.5)
        self.assertEqual(struct.unpack("<3H", result), (75, 0xffff, 75))

    def test_mode3_and_pressure_fields_only_on_active_str(self):
        labels = ["Duration", "Mode", "S.C.Press", "MaskPress.95"]
        fields = fields_for(labels, [1] * 4)
        active = record_for([60, 1, 12, 13])
        result = edf.make_synthetic_cpap_record(active, fields, "STR", 7.5)
        self.assertEqual(struct.unpack("<4H", result), (60, 30, 75, 75))
        empty = record_for([0xffff] * 4)
        self.assertEqual(edf.make_synthetic_cpap_record(empty, fields, "STR", 7.5), empty)

    def test_detailed_pressure_layout_sets_all_supported_channels(self):
        labels = list(edf.SYNTHETIC_CPAP_DETAILED_PRESSURE)
        fields = fields_for(labels, [1] * len(labels))
        result = edf.make_synthetic_cpap_record(record_for([0] * len(labels)), fields, "BRP", 7.5)
        self.assertEqual(struct.unpack("<4H", result), (75,) * 4)

    def test_absent_signal_header_uses_channel_sample_layout_and_crc(self):
        fields = fields_for(["Crc16"], [1])
        self.assertEqual(int(edf.empty_signal_header("Press.40ms", "BRP")[8]), 1500)
        self.assertEqual(int(edf.empty_signal_header("MaskPress.2s", "PLD")[8]), 30)
        self.assertEqual(int(edf.empty_signal_header("Duration", "STR")[8]), 1)
        self.assertEqual(int(edf.empty_signal_header("Crc16", "STR")[8]), 1)

    def test_air11_json_identity_and_crc_helpers_are_deterministic(self):
        source = (b'{"FlowGenerator":{"IdentificationProfiles":{"Product":{},'
                  b'"Software":{"PlatformIdentifier":46,"VariantIdentifier":12}}}}')
        updated = edf.restore_air11_json_identification(source, 46, 3)
        parsed = edf.json.loads(updated)
        software = parsed["FlowGenerator"]["IdentificationProfiles"]["Software"]
        self.assertEqual((software["PlatformIdentifier"], software["VariantIdentifier"]), (46, 3))
        self.assertEqual(edf.crc16(b"abc"), edf.crc16(b"abc"))

    def test_flow_pressure_bounds_sign_clipping_and_missing(self):
        flow = [-100.0] * 20 + [0.0] + [100.0] * 20 + [-1000.0, 1000.0, float("nan")]
        model = edf.FlowPressureModel(7.5, flow)
        got = [model.pressure(x) for x in [-1, 0, 1, -100, 100, float("nan")]]
        self.assertEqual(got, [7.504, 7.5, 7.489, 9.5, 9.5, 7.5])
        common = edf.FlowPressureModel(7.5, [-1.0, 0.0, 1.0])
        self.assertAlmostEqual(common.pressure(-1), 7.9)
        self.assertAlmostEqual(common.pressure(1), 6.4)
        self.assertAlmostEqual(edf.FlowPressureModel(7.5, [-1.0, 1.0]).pressure(-1), 7.9)
        self.assertAlmostEqual(edf.FlowPressureModel(7.5, [-1.0, 1.0]).pressure(1), 6.4)

    def test_rare_flow_peak_is_continuous_bounded_and_sign_symmetric(self):
        model = edf.FlowPressureModel(7.5, [-2.0, 2.0])
        self.assertAlmostEqual(model.pressure(1.8), 7.5)
        self.assertGreater(model.pressure(1.81), 7.5)
        self.assertAlmostEqual(model.pressure(2.4), 9.5)
        self.assertEqual(model.pressure(100), 9.5)
        self.assertEqual(model.pressure(-100), 9.5)
        self.assertEqual(model.pressure(float("nan")), 7.5)

    def test_flow_map_robust_reference_and_zero_baseline(self):
        model = edf.FlowPressureModel(7.5, [-1] * 20 + [-0.5, 0, 0.5] + [1] * 20 + [1.7])
        self.assertAlmostEqual(model.pressure(-1), 7.9)
        self.assertAlmostEqual(model.pressure(1), 6.4)
        self.assertEqual(model.pressure(0), 7.5)
        self.assertEqual(edf.FlowPressureModel(7.5, []).pressure(10), 7.5)

    def test_pressure_sample_conversion_clips_to_signal_range_and_skips_missing(self):
        fields = fields_for(["MaskPress.2s"], [3], pmin=0, pmax=20, dmin=0, dmax=200)
        record = record_for([0, 0xffff, 0])
        result = edf.set_signal_values(record, fields, "MaskPress.2s", [6.4, 7.5, 7.9])
        self.assertEqual(struct.unpack("<3H", result), (64, 0xffff, 79))

    def test_timestamp_alignment_requires_exact_session_and_record_timing(self):
        self.assertTrue(edf.same_edf_session("20261025_233436_BRP.edf", "20261025_233436_PLD.edf"))
        self.assertFalse(edf.same_edf_session("20261025_233436_BRP.edf", "20261025_233346_PLD.edf"))

    def test_inspiratory_reduces_expiratory_increases_and_reference_is_p95(self):
        model = edf.FlowPressureModel(7.5, [-1] * 20 + [-0.5, 0, 0.5] + [1] * 20 + [1.7])
        self.assertAlmostEqual(model.pressure(-1), 7.9)
        self.assertAlmostEqual(model.pressure(1), 6.4)
        self.assertEqual(model.pressure(0), 7.5)
        self.assertGreater(model.pressure(-1), 7.5)
        self.assertLess(model.pressure(1), 7.5)
        self.assertEqual(edf.FlowPressureModel(7.5, []).pressure(10), 7.5)

    def test_flow_pressure_does_not_change_therapy_fields_or_flow_samples(self):
        labels = ["Flow.40ms", "Press.40ms", "S.C.Press"]
        fields = fields_for(labels, [3, 3, 1], pmin=-100, pmax=100, dmin=0, dmax=200)
        flow = record_for([50, 100, 150] + [75, 75, 75] + [75])
        # The detailed converter only writes pressure signal samples.
        before = struct.unpack("<7H", flow)
        after = edf.set_signal_values(flow, fields, "Press.40ms", [7.9, 7.5, 6.4])
        values = struct.unpack("<7H", after)
        self.assertEqual(values[:3], before[:3])
        self.assertEqual(values[6], before[6])
        self.assertEqual(values[3:6], (108, 108, 106))


if __name__ == "__main__":
    unittest.main()
