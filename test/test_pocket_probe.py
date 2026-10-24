"""PocketVRX synthetic fixtures only. No board or live-video evidence."""

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pocket_probe as probe
from capture_iq_snapshot import decode, fnv1a


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.raw = bytes(range(256)) * 31 + bytes(range(254))
        self.packet = probe.pack(self.raw, "TEST_PATTERN", 7, 123, bytes(32))

    def test_roundtrip(self):
        raw, meta = probe.unpack(self.packet)
        self.assertEqual(raw, self.raw)
        self.assertEqual(meta["sequence"], 7)
        self.assertEqual(meta["source"], "TEST_PATTERN")

    def test_damage_and_bounds(self):
        for offset in (0, 12, probe.HEADER.size, probe.HEADER.size + 12, -1):
            damaged = bytearray(self.packet)
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                probe.unpack(damaged)
        for packet in (b"", self.packet[:-1], self.packet + b"extra"):
            with self.assertRaises(ValueError):
                probe.unpack(packet)
        with self.assertRaises(ValueError):
            probe.pack(b"", "TEST_PATTERN", 0, 0, bytes(32))

    def test_console_integrity(self):
        checksum = f"{fnv1a(self.raw):08x}"
        lines = [
            f"IQSNAP_BEGIN bytes=8190 rate_hz=40000000 format=Ihigh_Qlow fnv1a={checksum}",
            "IQSNAP_DATA offset=0 " + self.raw.hex(),
            f"IQSNAP_END fnv1a={checksum}",
        ]
        self.assertEqual(decode(lines)[0], self.raw)
        for changed in (
            lines[:-1],
            [lines[0], lines[1].replace("offset=0", "offset=1"), lines[2]],
            [lines[0], lines[1], "IQSNAP_END fnv1a=00000000"],
        ):
            with self.assertRaises(ValueError):
                decode(changed)

    def test_unknown_state(self):
        codes, mask = probe.strip(self.raw)
        self.assertEqual(len(codes), 4095)
        self.assertTrue(all(code <= 63 for code in codes))
        self.assertEqual(set(mask) - {0, 255}, set())
        self.assertEqual(mask[0], 0)
        with self.assertRaises(ValueError):
            probe.strip(b"short")

    def capture(self, fw="v5.0.123+aaaa"):
        checksum = f"{fnv1a(self.raw):08x}"
        return (
            "IQSNAP_BEGIN bytes=8190 rate_hz=40000000 format=Ihigh_Qlow "
            f"gain=78 lane=2 freq_mhz=5800 fw={fw} fnv1a={checksum}\n"
            f"IQSNAP_DATA offset=0 {self.raw.hex()}\n"
            f"IQSNAP_END fnv1a={checksum}\n"
        )

    def cli(self, source, output):
        return subprocess.run(
            [sys.executable, str(Path(probe.__file__)), str(source), str(output)],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )

    def test_cli_context_and_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hashes = []
            for index, fw in enumerate(("v5.0.123+aaaa", "v5.0.124+bbbb")):
                source, output = root / "log", root / str(index)
                source.write_text(self.capture(fw))
                result = self.cli(source, output)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads((output / "report.json").read_text())
                self.assertEqual(report["context"]["fw"], fw)
                _, meta = probe.unpack((output / "snapshot.pkiq").read_bytes())
                hashes.append(meta["context_sha256"])
                before = (output / "snapshot.pkiq").read_bytes()
                self.assertNotEqual(self.cli(source, output).returncode, 0)
                self.assertEqual((output / "snapshot.pkiq").read_bytes(), before)
            self.assertNotEqual(*hashes)

    def test_cli_refuses_invalid_inputs(self):
        capture = self.capture()
        invalid = [
            capture.replace("gain=78", "gain=abc"),
            capture.replace("freq_mhz=5800", "freq_mhz=5800.5"),
            capture.replace("gain=78", "gain=78 gain=79"),
            capture.replace("fw=v5.0.123+aaaa", "fw="),
            capture.replace("gain=78", "gain=78 junk"),
            capture.replace("gain=78", "gain=78=79"),
            capture + capture,
            "IQSNAP_REFUSED busy\n" + capture,
            capture + "IQSNAP_REFUSED busy\n",
            "x" * (probe.MAX_LOG + 1),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for text in invalid:
                source, output = root / "log", root / "output"
                source.write_text(text)
                self.assertNotEqual(self.cli(source, output).returncode, 0)
                self.assertFalse(output.exists())
            fifo = root / "fifo"
            os.mkfifo(fifo)
            for source in (fifo, root, Path("/dev/null")):
                self.assertNotEqual(self.cli(source, root / "output").returncode, 0)

    def test_independent_p64_reference(self):
        # C5VRX P64's two-lookup routing, evaluated as 64 separate streams.
        # Source/credits: tools/pocket_probe.py and PROVENANCE.md.
        rng = random.Random(64)
        table = probe.table_words()
        for raw in (
            self.raw,
            bytes(probe.MAX_PAYLOAD),
            rng.randbytes(probe.MAX_PAYLOAD),
        ):
            streams = []
            for initial in range(64):
                state, output = initial, bytearray()
                for first, second in zip(raw[::2], raw[1::2]):
                    address = (
                        (first >> 4)
                        | ((first & 15) << 4)
                        | ((second & 128) << 1)
                        | ((second & 8) << 6)
                    )
                    token = table[address] // 4096
                    entry = table[16 * state + token]
                    output.append(entry % 64)
                    state = (entry // 64) % 64
                streams.append(output)
            codes, mask = probe.strip(raw)
            self.assertEqual(codes, streams[0])
            expected = bytes(
                255 if len(set(column)) == 1 else 0 for column in zip(*streams)
            )
            self.assertEqual(mask, expected)


if __name__ == "__main__":
    unittest.main()
