"""Unit tests for classification, prioritization, retrieval, prediction and recommendation."""
from src.agents.classifier_agent import rule_classify
from src.rag.hybrid_retriever import hybrid_search
from src.services import ml_models, prioritization
from src.services.recommendation import rank_strategies


def test_rule_classifier_extracts_attributes():
    c = rule_classify("Ransomware hit our tier-2 auto parts supplier in Germany, no backup supplier, production halted")
    assert c["disruption_type"] == "Cyber Attack"
    assert c["industry"] == "Automotive"
    assert c["supplier_region"] == "Europe"
    assert c["supplier_tier"] == 2
    assert c["has_backup_supplier"] is False
    assert c["estimated_severity"] >= 4


def test_priority_ordering():
    high = prioritization.score(5, 80, 20_000_000, 1, False)
    low = prioritization.score(1, 5, 50_000, 4, True)
    assert high["priority_level"] == "P1" and low["priority_level"] == "P4"
    assert high["priority_score"] > low["priority_score"]
    assert abs(sum(high["factor_contributions"].values()) - high["priority_score"]) < 0.2


def test_batch_ranked():
    out = prioritization.prioritize_batch([
        {"id": "a", "disruption_severity": 1, "production_impact_pct": 5, "revenue_loss_usd": 1e4},
        {"id": "b", "disruption_severity": 5, "production_impact_pct": 90, "revenue_loss_usd": 5e7}])
    assert [o["id"] for o in out] == ["b", "a"] and out[0]["rank"] == 1


def test_hybrid_search_respects_filters():
    res = hybrid_search("flooding at electronics plant", top_k=5,
                        filters={"industry": ["Aerospace"], "min_severity": 4})
    assert res["results"]
    assert all(r["industry"] == "Aerospace" and r["disruption_severity"] >= 4 for r in res["results"])


def test_retrieval_modes_return_scores():
    for mode in ("semantic", "keyword", "hybrid"):
        res = hybrid_search("ransomware cyber attack", top_k=3, mode=mode)
        assert len(res["results"]) == 3
        assert all(0 <= r["hybrid_score"] <= 1.0001 for r in res["results"])


def test_predictions_have_ranges(profile):
    p = ml_models.predict(profile)
    for t in ("production_impact_pct", "revenue_loss_usd", "full_recovery_days"):
        assert p[t]["low_p10"] <= p[t]["predicted"] <= p[t]["high_p90"]
    assert 0 <= p["high_impact_probability"] <= 1


def test_severity_increases_predicted_recovery(profile):
    low = ml_models.predict({**profile, "disruption_severity": 1})["full_recovery_days"]["predicted"]
    high = ml_models.predict({**profile, "disruption_severity": 5})["full_recovery_days"]["predicted"]
    assert high > low


def test_strategy_ranking(profile):
    cases = hybrid_search("typhoon electronics supplier", top_k=10)["results"]
    ranked = rank_strategies(cases, ml_models.predict_by_response(profile), {"Customer Delay": 1.15})
    assert ranked[0]["rank"] == 1
    assert ranked == sorted(ranked, key=lambda r: (not r["feasible_now"], -r["strategy_score"]))


def test_plan_strategy_is_top_ranked_not_llm_choice(profile):
    from src.services.recommendation import generate_plan
    cases = hybrid_search("typhoon electronics supplier", top_k=10)["results"]
    ranked = rank_strategies(cases, ml_models.predict_by_response(profile))
    plan = generate_plan("typhoon at chip supplier", ranked, cases)
    assert plan["recommended_strategy"] == ranked[0]["response_type"]
    assert plan["fallback_strategy"] == ranked[1]["response_type"]
    assert "CHOSEN STRATEGY" in plan["fact_sheet"]


def test_no_backup_never_recommends_alternative_supplier(profile):
    """With no qualified backup, Alternative Supplier is ranked last with a note, never the recommendation or fallback."""
    from src.services.recommendation import generate_plan
    cases = hybrid_search("typhoon electronics supplier", top_k=10)["results"]
    what_if = ml_models.predict_by_response(profile)
    ranked = rank_strategies(cases, what_if, has_backup=False)
    alt = next(r for r in ranked if r["response_type"] == "Alternative Supplier")
    assert alt["rank"] == len(ranked) and alt["feasible_now"] is False and alt["feasibility_note"]
    plan = generate_plan("typhoon at chip supplier, no backup supplier", ranked, cases, profile=profile)
    assert "Alternative Supplier" not in (plan["recommended_strategy"], plan["fallback_strategy"])
    assert not any("activate an alternative supplier" in a.lower() for a in plan["immediate_actions"])
    assert "NOT AN IMMEDIATE OPTION - Alternative Supplier" in plan["fact_sheet"]
    with_backup = rank_strategies(cases, what_if, has_backup=True)
    assert all(r["feasible_now"] for r in with_backup)


def test_sanctions_pharma_no_backup_scenario():
    """Regression: a moderate sanctions delay at a French pharma supplier with no approved backup was answered with
    Alternative Supplier (scored 95 vs 62 for Inventory Buffer)."""
    from src.agents.classifier_agent import rule_classify
    from src.agents.investigation_agent import investigate
    from src.agents.response_agent import plan_response
    q = ("New sanctions and export restrictions have moderately slowed shipments from our Tier-1 medium-sized pharmaceutical "
         "supplier in France. Customs authorities are holding some consignments of active ingredients for additional checks, "
         "and the supplier is waiting for revised licences. Hospitals we serve have not run short yet, but our safety stock "
         "is thinning. We have no backup supplier approved for these ingredients.")
    c = rule_classify(q)
    assert c["has_backup_supplier"] is False
    inv = investigate(q, c)
    out = plan_response(q, inv["profile"], inv["similar_cases"], pool=inv.get("strategy_pool"))
    assert out["plan"]["recommended_strategy"] != "Alternative Supplier"
    assert out["strategy_ranking"][-1]["response_type"] == "Alternative Supplier"


def test_unsupported_numbers_detected():
    from src.services.recommendation import unsupported_numbers
    facts = "expected full recovery ~86 days, expected revenue loss $2.3M, supplier-change risk 63%"
    assert unsupported_numbers("Recovery in ~86 days with a loss of about $2.3M (63% risk).", facts) == []
    bad = unsupported_numbers("Recovery ranges from 37-211 days and loss is $9M.", facts)
    assert "37 days" in bad and "211 days" in bad and any("USD" in b for b in bad)
    assert unsupported_numbers("Confirm capacity within 7 days.", facts) == []  # short plan timelines allowed
