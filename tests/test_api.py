from fastapi.testclient import TestClient

from src.logistics_eta.api import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["eta_model_loaded"] is True
    assert response.json()["delay_model_loaded"] is True


def test_eta_prediction():
    response = client.post(
        "/predict/eta",
        json={"shipment_id": "SHP-2026-000001"}
    )

    assert response.status_code == 200

    data = response.json()

    assert data["prediction_type"] == "ETA"
    assert data["shipment_id"] == "SHP-2026-000001"
    assert data["remaining_delivery_minutes"] >= 0


def test_delay_prediction():
    response = client.post(
        "/predict/delay",
        json={"shipment_id": "SHP-2026-000001"}
    )

    assert response.status_code == 200

    data = response.json()

    assert data["prediction_type"] == "DELAY"
    assert isinstance(data["is_delay_likely"], bool)
    assert 0 <= data["delay_probability"] <= 1


def test_invalid_shipment_id():
    response = client.post(
        "/predict/eta",
        json={"shipment_id": "INVALID-ID"}
    )

    assert response.status_code == 422


def test_missing_shipment_id():
    response = client.post(
        "/predict/eta",
        json={}
    )

    assert response.status_code == 422