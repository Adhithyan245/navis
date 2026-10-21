"""Shared test setup."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _no_photon_network():
    """Location search asks Photon when it has a bias; tests that care mock
    it themselves, everyone else gets no Photon results instead of a live call."""
    from apps.api.services.geocoding import GeocodingService

    with patch.object(GeocodingService, "_photon_forward", AsyncMock(return_value=[])):
        yield
