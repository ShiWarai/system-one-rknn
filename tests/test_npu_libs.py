import os
import tempfile
import unittest

from app.npu_libs import UnsupportedBoard, install_runtime_libraries, main, runtime_libraries


class NpuLibsTest(unittest.TestCase):
    def test_empty_board_is_rejected(self):
        with self.assertRaises(UnsupportedBoard):
            runtime_libraries("")
        with self.assertRaises(UnsupportedBoard):
            runtime_libraries("   ")

    def test_unknown_board_is_rejected(self):
        with self.assertRaises(UnsupportedBoard) as caught:
            runtime_libraries("rk3568")
        self.assertIn("rk3568", str(caught.exception))
        with tempfile.TemporaryDirectory() as dest:
            with self.assertRaises(SystemExit) as exited:
                main(["npu_libs.py", "rk3568", "arm64", dest])
            self.assertIn("rk3568", str(exited.exception))
            self.assertEqual(os.listdir(dest), [])

    def test_usage_requires_board_arch_and_dest(self):
        with self.assertRaises(SystemExit):
            main(["npu_libs.py"])

    def test_rk3588_names_are_the_image_paths(self):
        names = [name for name, _url, _digest in runtime_libraries("rk3588")]
        self.assertEqual(names, ["librknnrt-2.3.2.so", "librkllmrt-1.3.1.so"])

    def test_non_arm64_installs_nothing(self):
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(install_runtime_libraries("rk3588", "amd64", dest), [])
            self.assertEqual(install_runtime_libraries("rk3588", "", dest), [])
            self.assertEqual(os.listdir(dest), [])

    def test_rk3588_arm64_fetches_pinned_runtimes(self):
        with tempfile.TemporaryDirectory() as dest:
            paths = install_runtime_libraries("rk3588", "arm64", dest)
            by_name = {}
            for path in paths:
                with open(path, "rb") as handle:
                    by_name[os.path.basename(path)] = handle.read()
            self.assertEqual(set(by_name), {"librknnrt-2.3.2.so", "librkllmrt-1.3.1.so"})
            for blob in by_name.values():
                self.assertEqual(blob[:4], b"\x7fELF")
                self.assertEqual(blob[18:20], b"\xb7\x00")
            self.assertIn(b"librknnrt version: 2.3.2", by_name["librknnrt-2.3.2.so"])
            self.assertIn(b"RKLLM SDK (version: 1.3.1", by_name["librkllmrt-1.3.1.so"])
            self.assertEqual(install_runtime_libraries("rk3588", "arm64", dest), paths)
