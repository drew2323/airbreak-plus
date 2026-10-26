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


if __name__ == "__main__":
    unittest.main()
