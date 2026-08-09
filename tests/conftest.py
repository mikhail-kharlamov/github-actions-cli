from __future__ import annotations

import pytest

from gh_actions_cli import i18n


@pytest.fixture(autouse=True)
def _reset_language():
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
