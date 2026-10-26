import unittest

from lib.cargo import publishable_members

METADATA = {
    "workspace_members": ["itinera 0.2.0", "itinera-core 0.2.0", "xtask 0.0.0"],
    "packages": [
        {"id": "itinera 0.2.0", "name": "itinera"},
        {"id": "itinera-core 0.2.0", "name": "itinera-core", "publish": None},
        {"id": "xtask 0.0.0", "name": "xtask", "publish": []},
        {"id": "regex 1.0.0", "name": "regex"},
    ],
}


class PublishableMembers(unittest.TestCase):
    def test_only_members_that_may_be_published_are_kept(self):
        names = [package["name"] for package in publishable_members(METADATA)]
        self.assertEqual(names, ["itinera", "itinera-core"])


if __name__ == "__main__":
    unittest.main()
