#!/usr/bin/env python3
import os
import sys

_repo_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_src_dir = os.path.join(_repo_dir, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)
if _repo_dir not in sys.path:
    sys.path.insert(0, _repo_dir)


import unittest

# Import test modules
import tests.test_validation as t_val
import tests.test_models as t_mod
import tests.test_events as t_evt
import tests.test_circadian as t_circ
import tests.test_color as t_col

class LumaTrayUnitTests(unittest.TestCase):
    def test_validation_clamping(self):
        t_val.test_clamping()

    def test_destructive_codes_blocked(self):
        # Adapt pytest.raises for unittest
        from lumatray.core.errors import ValidationError
        from lumatray.core.validation import DESTRUCTIVE_VCP_CODES, validate_vcp_request
        for code in DESTRUCTIVE_VCP_CODES:
            with self.assertRaises(ValidationError):
                validate_vcp_request(code, 1)

    def test_safe_codes_allowed(self):
        t_val.test_safe_vcp_codes_allowed()

    def test_models_display_identity(self):
        t_mod.test_display_identity_serialization()

    def test_models_capability_report(self):
        t_mod.test_capability_report()

    def test_models_profile(self):
        t_mod.test_profile_serialization()

    def test_event_bus(self):
        t_evt.test_event_bus()

    def test_circadian_evaluation(self):
        t_circ.test_circadian_evaluation()

    def test_auto_mode_toggle(self):
        t_circ.test_auto_mode_toggle()

    def test_kelvin_to_rgb(self):
        t_col.test_kelvin_to_rgb_mapping()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(LumaTrayUnitTests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
