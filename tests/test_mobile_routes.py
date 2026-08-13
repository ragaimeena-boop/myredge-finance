import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_base_mobile_header_and_drawer(tmp_path, monkeypatch):
    """Verify that all main routes contain the mobile top header, hamburger button, and drawer overlay."""
    db_file = tmp_path / "test_mobile.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    routes_to_check = [
        "/",
        "/reports/weekly",
        "/reports/monthly",
        "/reports/yearly",
        "/transactions",
        "/investments",
        "/subscriptions",
    ]

    with TestClient(app) as client:
        for route in routes_to_check:
            response = client.get(route)
            assert response.status_code == 200
            
            # Viewport meta tag
            assert 'name="viewport"' in response.text
            assert 'width=device-width' in response.text

            # Mobile Header Elements
            assert 'class="mobile-header"' in response.text
            assert 'id="mobileMenuToggle"' in response.text
            assert 'class="mobile-hamburger-btn"' in response.text

            # Mobile Drawer Elements
            assert 'id="mobileNavOverlay"' in response.text
            assert 'id="mobileNavDrawer"' in response.text
            assert 'id="mobileDrawerClose"' in response.text
            
            # Desktop Sidebar Elements
            assert 'class="sidebar desktop-sidebar"' in response.text

def test_transactions_responsive_form_class(tmp_path, monkeypatch):
    """Verify transactions page renders filter-form-mobile form container."""
    db_file = tmp_path / "test_mobile.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    with TestClient(app) as client:
        response = client.get("/transactions")
        assert response.status_code == 200
        assert 'class="filter-form-mobile"' in response.text

def test_pwa_manifest_and_sw_routes(tmp_path, monkeypatch):
    """Verify PWA manifest.json and sw.js routes return correct content types and data."""
    db_file = tmp_path / "test_mobile.db"
    monkeypatch.setattr("app.config.settings.DATABASE_URL", f"sqlite:///{db_file}")

    with TestClient(app) as client:
        # Check manifest endpoint
        manifest_res = client.get("/manifest.json")
        assert manifest_res.status_code == 200
        assert "application/manifest+json" in manifest_res.headers.get("content-type", "")
        assert "MYREDGE" in manifest_res.text
        assert "standalone" in manifest_res.text

        # Check service worker endpoint
        sw_res = client.get("/sw.js")
        assert sw_res.status_code == 200
        assert "javascript" in sw_res.headers.get("content-type", "")
        assert "CACHE_NAME" in sw_res.text

        # Check HTML contains PWA links
        home_res = client.get("/")
        assert 'rel="manifest"' in home_res.text
        assert 'navigator.serviceWorker.register' in home_res.text
