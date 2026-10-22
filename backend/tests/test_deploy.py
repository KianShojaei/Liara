import json
from pathlib import Path

from app.deploy.advisor import PlanAdvisor
from app.deploy.analyzer import ProjectAnalyzer
from app.liara.models import ProjectPlan

ROOT = Path(__file__).resolve().parents[2]


def test_analyzes_demo_app():
    analysis = ProjectAnalyzer(ROOT / "demo" / "shop-demo").analyze()
    assert analysis.platform == "node"
    assert analysis.port == 3000
    assert "FAULT_MODE" in analysis.env_keys and "SHOP_API_KEY" in analysis.secret_env_keys
    assert analysis.health_path == "/health"


def test_detects_flask_and_postgres(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("flask==3.0\npsycopg2-binary\n")
    (tmp_path / "app.py").write_text("app.run(port=5055)\n")
    analysis = ProjectAnalyzer(tmp_path).analyze()
    assert (
        analysis.platform == "flask"
        and analysis.port == 5055
        and analysis.databases == ["postgres"]
    )


def test_detects_next_and_liara_json(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"next": "14", "react": "18"}})
    )
    (tmp_path / "liara.json").write_text(json.dumps({"port": 3100}))
    analysis = ProjectAnalyzer(tmp_path).analyze()
    assert analysis.platform == "next" and analysis.port == 3100 and analysis.has_liara_json


def test_plan_advice_cost_and_runway():
    catalog = [
        ProjectPlan.model_validate(
            {
                "available": True,
                "region": "iran",
                "RAM": {"amount": r},
                "CPU": {"amount": 1},
                "price": p,
            }
        )
        for r, p in ((0.25, 0), (0.5, 208), (1, 416))
    ]
    for plan, pid in zip(catalog, ("free", "small", "medium"), strict=True):
        plan.plan_id = pid
    analysis = ProjectAnalyzer(Path(__file__).resolve().parents[2] / "demo" / "shop-demo").analyze()
    advice = PlanAdvisor(catalog, balance=50_000).advise(analysis)
    assert advice.recommended_plan_id == "small"
    small = next(o for o in advice.options if o.plan_id == "small")
    assert small.monthly_price == 208 * 720 and 200 < small.runway_hours < 300
    poor = PlanAdvisor(catalog, balance=100).advise(analysis)
    assert not poor.balance_ok
