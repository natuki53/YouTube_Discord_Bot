import importlib
import pkgutil
import unittest

import bot


class ModuleImportTests(unittest.TestCase):
    def test_all_bot_modules_are_importable(self):
        modules = [
            module.name
            for module in pkgutil.walk_packages(bot.__path__, f"{bot.__name__}.")
        ]

        for module_name in modules:
            with self.subTest(module=module_name):
                importlib.import_module(module_name)


if __name__ == "__main__":
    unittest.main()
