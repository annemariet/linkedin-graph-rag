"""Tests for main application."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


def test_root_endpoint():
    """Test the root endpoint."""
    client = TestClient(app)
    response = client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Code Review Assistant API"
    assert data["version"] == "0.1.0"
    assert data["docs"] == "/docs"


def test_health_endpoint():
    """Test the health check endpoint."""
    client = TestClient(app)
    response = client.get("/api/v1/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["message"] == "Service is running"