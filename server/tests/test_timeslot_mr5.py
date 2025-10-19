"""
DEPRECATED: This test file tested internal implementation of the deprecated create_form tool.
The functionality is now covered by:
- test_gpt_actions.py::test_gpt_create_form_timeslots
- test_timeslot_bugs_reproduction.py

This file can be safely removed.
"""

import pytest


@pytest.mark.skip(reason="Deprecated - tests removed with create_form tool")
def test_deprecated():
    """Placeholder for deprecated test file"""
    pass
