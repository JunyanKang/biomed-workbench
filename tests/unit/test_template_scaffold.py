import hashlib
import unittest

from biomed_workbench.modules.index import BUILTIN_ROOT
from tools.scaffold_bioinformatics_templates import scaffold


class BioinformaticsTemplateScaffoldTests(unittest.TestCase):
    def test_scaffold_does_not_replace_existing_module_owned_templates(self):
        template = BUILTIN_ROOT / "single-cell-foundation-workflow" / "templates" / "scanpy_foundation.py"
        before = hashlib.sha256(template.read_bytes()).hexdigest()

        eligible, changed = scaffold(check=False)

        self.assertEqual(changed, [])
        self.assertEqual(eligible, 0)
        self.assertEqual(hashlib.sha256(template.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
