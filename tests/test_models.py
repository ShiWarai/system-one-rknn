import unittest

from app.download import model_files
from app.server import selected_models


class ModelSelectionTest(unittest.TestCase):
    def test_default_is_both(self):
        self.assertEqual(selected_models("laya,kev"), ["laya", "kev"])

    def test_aliases_and_duplicates(self):
        self.assertEqual(selected_models("laya-multilingual, kev-0.8b, laya"), ["laya", "kev"])
        self.assertEqual(selected_models("kev"), ["kev"])

    def test_unknown_name(self):
        with self.assertRaises(SystemExit):
            selected_models("lev")

    def test_empty_value(self):
        with self.assertRaises(SystemExit):
            selected_models(" , ")

    def test_download_list_follows_the_selection(self):
        kev_only = model_files("laya-repo", "kev-repo", ["kev"])
        self.assertTrue(all(folder == "kev" for _repo, folder, _name in kev_only))
        self.assertIn("kev-0.8b-w8a8-opt0-ctx320.rkllm", [name for _r, _f, name in kev_only])
        self.assertNotIn("laya", [folder for _r, folder, _n in kev_only])

        laya_only = model_files("laya-repo", "kev-repo", ["laya"])
        self.assertEqual({folder for _r, folder, _n in laya_only}, {"laya"})


if __name__ == "__main__":
    unittest.main()
