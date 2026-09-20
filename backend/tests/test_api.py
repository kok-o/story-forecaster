import pytest
from fastapi.testclient import TestClient
from story_forecaster.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_api_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_api_work_and_chapters(client):
    res_work = client.get("/api/work")
    assert res_work.status_code == 200
    work_data = res_work.json()
    assert work_data["chapters_count"] >= 23
    assert work_data["scenes_count"] >= 192

    res_chs = client.get("/api/chapters")
    assert res_chs.status_code == 200
    chs = res_chs.json()
    assert len(chs) >= 23
    assert chs[0]["ordinal"] == 1
    assert chs[-1]["ordinal"] >= 23

def test_api_canon_summary(client):
    res = client.get("/api/canon/summary?cutoff_chapter=23")
    assert res.status_code == 200
    data = res.json()
    assert "distribution" in data
    assert "elements" in data
    assert data["total_canon_elements_tracked"] > 0

def test_api_retrieval_search(client):
    res = client.post("/api/retrieval/search", json={
        "query": "Хорадримский Куб",
        "cutoff_chapter": 23,
        "top_k": 3
    })
    assert res.status_code == 200
    results = res.json()
    assert len(results) > 0
    for r in results:
        assert r["chapter_num"] <= 23

def test_api_forecast_and_backtest(client):
    # Test forecast endpoint
    res_fc = client.post("/api/forecast", json={
        "cutoff_chapter": 23,
        "num_candidates": 3
    })
    assert res_fc.status_code == 200
    fc_data = res_fc.json()
    assert len(fc_data["candidates"]) == 3

    # Test backtest endpoint
    res_bt = client.post("/api/backtest", json={
        "cutoff_chapter": 22
    })
    assert res_bt.status_code == 200
    bt_data = res_bt.json()
    assert bt_data["best_at_1"]["event_f1"] > 0.6
    assert bt_data["oracle_at_k"]["event_f1"] > 0.6

def test_api_author_precedents(client):
    res = client.get("/api/author/precedents?tags=blackmail_counterattack,system_exploitation")
    assert res.status_code == 200
    data = res.json()
    assert data["author"] == "N.B."
    assert len(data["abstracted_transitions"]) > 0
    assert len(data["corpus_excerpts"]) > 0

def test_frontend_static_serving(client):
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "Story Forecaster" in res_index.text

    res_css = client.get("/styles.css")
    assert res_css.status_code == 200
    assert "--bg-primary" in res_css.text

    res_js = client.get("/app.js")
    assert res_js.status_code == 200
    assert "loadForecast" in res_js.text

def test_api_memory_snapshot(client):
    res = client.get("/api/memory/snapshot?cutoff_chapter=23")
    assert res.status_code == 200
    data = res.json()
    assert "active_threads" in data
    assert "active_characters" in data
    assert "chapter_num" in data

def test_api_validation_errors(client):
    # Invalid cutoff_chapter <= 0
    res = client.get("/api/memory/snapshot?cutoff_chapter=0")
    assert res.status_code == 422

    # Invalid num_candidates <= 0
    res_fc = client.post("/api/forecast", json={"cutoff_chapter": 23, "num_candidates": 0})
    assert res_fc.status_code == 422

    # Invalid provider name
    res_pv = client.post("/api/forecast", json={"cutoff_chapter": 23, "provider_name": "unknown_ai"})
    assert res_pv.status_code == 422

def test_api_forecast_gemini_unconfigured_error():
    client = TestClient(app)
    res = client.post("/api/forecast", json={"cutoff_chapter": 23, "provider_name": "gemini"})
    assert res.status_code == 400
    assert "Gemini provider selected, but GEMINI_API_KEY is not set" in res.json()["detail"]

def test_api_backtest_gemini_unconfigured_error():
    client = TestClient(app)
    res = client.post("/api/backtest", json={"cutoff_chapter": 22, "provider_name": "gemini"})
    assert res.status_code == 400
    assert "Gemini provider selected, but GEMINI_API_KEY is not set" in res.json()["detail"]



