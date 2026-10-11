"""Tests for similar-case search in the investigation agent, plan list cleaning and backup-supplier detection."""
from src.agents.classifier_agent import rule_classify
from src.agents.investigation_agent import investigate, retrieval_query

EVENT = "A fire at our Tier-1 chip supplier in Taiwan has shut down a line."
LONG = EVENT + " We have 10 days of inventory remaining. Two alternative ports are available. Production could fall by 40%."


def test_retrieval_query_keeps_event_and_drops_strategy_words():
    q = retrieval_query(LONG)
    assert q.startswith(EVENT)
    for word in ("inventory", "alternative", "Production"):
        assert word not in q[len(EVENT):]
    assert "40%" in q  # numbers and other details are kept


def test_retrieval_query_keeps_first_sentence_even_if_it_mentions_inventory():
    text = "A warehouse fire destroyed our finished-goods inventory in Texas. We have a backup supplier."
    assert retrieval_query(text).startswith("A warehouse fire destroyed our finished-goods inventory in Texas.")


def test_single_sentence_query_is_unchanged():
    assert retrieval_query(EVENT) == EVENT


def _cls(**kw):
    return {"disruption_type": "Cyber Attack", "industry": "Automotive", "supplier_region": "Europe",
            "estimated_severity": 4, **kw}


def test_severity_band_is_applied_to_search():
    inv = investigate("Ransomware hit our Tier-1 auto supplier in Germany.", _cls(), top_k=10)
    assert inv["filters_applied"]["min_severity"] == 3 and inv["filters_applied"]["max_severity"] == 5
    assert all(3 <= c["disruption_severity"] <= 5 for c in inv["similar_cases"])


def test_user_severity_filter_is_never_overridden():
    inv = investigate("Ransomware hit our Tier-1 auto supplier in Germany.", _cls(), top_k=10,
                      user_filters={"min_severity": 5})
    assert inv["filters_applied"]["min_severity"] == 5
    assert "max_severity" not in inv["filters_applied"]
    assert all(c["disruption_severity"] == 5 for c in inv["similar_cases"])


def test_thin_combinations_still_return_evidence_and_say_how():
    inv = investigate("Sanctions blocked our aerospace supplier.",
                      _cls(disruption_type="Geopolitical", industry="Aerospace", supplier_region="South America",
                           estimated_severity=5), top_k=10)
    assert len(inv["similar_cases"]) > 0
    assert isinstance(inv["relaxations"], list)


def test_plan_lists_drop_null_entries(monkeypatch):
    from src.services import llm_client
    from src.services.recommendation import generate_plan
    ranked = [{"response_type": "Alternative Supplier", "rank": 1, "strategy_score": 80, "evidence_cases": 5,
               "expected_full_recovery_days": 90.0, "expected_revenue_loss_usd": 1e6, "supplier_change_risk": 0.3,
               "historical": None, "predicted": None},
              {"response_type": "Customer Delay", "rank": 2, "strategy_score": 60, "evidence_cases": 2,
               "expected_full_recovery_days": 100.0, "expected_revenue_loss_usd": 1e6, "supplier_change_risk": 0.3,
               "historical": None, "predicted": None}]
    monkeypatch.setattr(llm_client, "complete_json", lambda *a, **k: {
        "rationale": "Chosen strategy fits.", "immediate_actions": ["Call suppliers", None, "None", " "],
        "recovery_plan": ["Week 1: start", None], "risks": ["Delay risk", "null"], "cited_cases": []})
    plan = generate_plan("test", ranked, [])
    for key in ("immediate_actions", "recovery_plan", "risks"):
        assert all(x.strip().lower() not in ("none", "null", "") for x in plan[key]), plan[key]
    assert plan["immediate_actions"] == ["Call suppliers"]


def test_rule_classifier_backup_semantics():
    assert rule_classify("Our sole Tier-2 supplier in Japan was hit. Neither is currently qualified.")["has_backup_supplier"] is False
    assert rule_classify("We have no fully qualified backup supplier.")["has_backup_supplier"] is False
    assert rule_classify("We have a qualified backup supplier ready.")["has_backup_supplier"] is True


def test_strategy_pool_is_large_and_matches_backup_status():
    inv = investigate("Ransomware hit our Tier-1 auto supplier in Germany. We have no backup supplier.", _cls(),
                      overrides={"has_backup_supplier": False}, top_k=10)
    pool = inv["strategy_pool"]
    assert pool and pool["size"] >= 30 and len(inv["similar_cases"]) == 10
    assert pool["filters"]["has_backup_supplier"] is False
    assert "no backup supplier" in pool["description"]


def test_plan_compares_on_pool_and_quotes_the_headline_numbers(profile):
    from src.agents.response_agent import plan_response
    inv = investigate("Ransomware hit our Tier-1 auto supplier in Germany.", _cls(), overrides=profile, top_k=10)
    out = plan_response("Ransomware hit our Tier-1 auto supplier in Germany.", inv["profile"], inv["similar_cases"],
                        pool=inv["strategy_pool"])
    best = out["strategy_ranking"][0]
    assert out["basis"]["comparable_cases"] > 10 and best["evidence_total"] == out["basis"]["comparable_cases"]
    full = round(best["predicted"]["predicted_full_recovery_days"])
    assert f"~{full} days" in out["plan"]["fact_sheet"]          # the plan's recovery figure is the model's
    assert f"~{full} days" in out["plan"]["recovery_plan"][1]    # ...and so is the template timeline
    shown = {c["disruption_id"] for c in inv["similar_cases"]}
    assert set(out["plan"]["cited_cases"]) <= shown                # examples quoted are cases the user can see


def test_fact_sheet_carries_the_headline_estimates():
    from src.services.recommendation import build_fact_sheet
    row = {"response_type": "Alternative Supplier", "rank": 1, "strategy_score": 80, "evidence_cases": 50,
           "evidence_total": 200, "expected_full_recovery_days": 90.0, "expected_revenue_loss_usd": 1e6,
           "supplier_change_risk": 0.3, "historical": None,
           "predicted": {"predicted_full_recovery_days": 123.4, "predicted_partial_recovery_days": 36.2,
                         "supplier_change_probability": 0.4, "predicted_revenue_loss_usd": 4.9e6}}
    headline = {"production_impact_pct": {"predicted": 52, "low_p10": 38, "high_p90": 64},
                "revenue_loss_usd": {"predicted": 4.89e6, "low_p10": 1.74e6, "high_p90": 14.15e6}}
    sheet = build_fact_sheet([row], [], headline)
    assert "~123 days" in sheet and "~36 days" in sheet and "of the 200 comparable past cases" in sheet
    assert "~52%" in sheet and "$4.9M" in sheet


def test_close_call_note_only_when_scores_are_near():
    from src.services.recommendation import close_call
    near = [{"response_type": "A", "strategy_score": 70.0}, {"response_type": "B", "strategy_score": 67.0}]
    far = [{"response_type": "A", "strategy_score": 80.0}, {"response_type": "B", "strategy_score": 60.0}]
    assert "Close call" in close_call(near) and close_call(far) is None


def test_what_if_numbers_equal_the_headline_prediction():
    """The plan quotes predict_by_response(); the headline and timeline use predict(). They must agree exactly."""
    from src.services import ml_models
    for sev in (1, 3, 5):
        for backup in (True, False):
            prof = {"disruption_type": "Port Congestion", "industry": "Electronics", "supplier_tier": 2,
                    "supplier_region": "Asia-Pacific", "supplier_size": "Large", "has_backup_supplier": backup,
                    "disruption_severity": sev}
            for w in ml_models.predict_by_response(prof):
                p = ml_models.predict({**prof, "response_type": w["response_type"]})
                assert w["predicted_full_recovery_days"] == p["full_recovery_days"]["predicted"]
                assert w["predicted_partial_recovery_days"] == p["partial_recovery_days"]["predicted"]
                assert w["supplier_change_probability"] == round(p["supplier_change_probability"], 4)


def test_fact_sheet_does_not_invite_counting_strategies_on_ten_cases():
    from src.services.recommendation import build_fact_sheet
    cases = [{"disruption_id": f"DIS-{i:06d}", "disruption_type": "Port Congestion", "industry": "Electronics",
              "disruption_severity": 4, "production_impact_pct": 40.0, "revenue_loss_usd": 2e6, "response_type": "Customer Delay",
              "full_recovery_days": 120, "partial_recovery_days": 40, "permanent_supplier_change": False} for i in range(10)]
    row = {"response_type": "Inventory Buffer", "rank": 1, "strategy_score": 80, "evidence_cases": 80, "evidence_total": 312,
           "expected_full_recovery_days": 100.0, "expected_revenue_loss_usd": 1e6, "supplier_change_risk": 0.3,
           "historical": None, "predicted": None}
    sheet = build_fact_sheet([row], cases)
    assert "Responses used" not in sheet and "used in 80 of the 312 comparable past cases" in sheet


def test_broken_rationale_falls_back_to_template(monkeypatch):
    from src.services import llm_client
    from src.services.recommendation import generate_plan, _wording_ok
    ranked = [{"response_type": "Alternative Supplier", "rank": 1, "strategy_score": 80, "evidence_cases": 5,
               "evidence_total": 50, "expected_full_recovery_days": 90.0, "expected_revenue_loss_usd": 1e6,
               "supplier_change_risk": 0.3, "historical": None, "predicted": None}]
    monkeypatch.setattr(llm_client, "complete_json", lambda *a, **k: {
        "rationale": "The Alternative Supplier plan fits; loss is $1.9M estimate).", "immediate_actions": ["Call suppliers"],
        "recovery_plan": ["Week 1: start"], "risks": ["Delay risk"], "cited_cases": []})
    plan = generate_plan("test", ranked, [])
    assert "loss is $1.9M" not in plan["rationale"]
    assert plan["rationale"].startswith("Alternative Supplier has the best overall score")
    assert "Rationale replaced" in plan["guardrail_note"]
    assert _wording_ok(plan["rationale"])
    assert _wording_ok("Fits well (see [unverified case]).") and not _wording_ok("Cut off mid sentence")


# ---- override conflict notes: quiet unless the text explicitly points elsewhere ----
def test_override_notes_flag_real_conflicts():
    from src.agents.classifier_agent import override_conflicts as oc
    fire = "A factory fire has halted the plant of our Tier-2 pharmaceutical supplier in India for four weeks."
    assert any("Factory Incident" in n for n in oc({"disruption_type": "Natural Disaster"}, fire))
    assert oc({"supplier_tier": 3}, "Our Tier-1 supplier lost power.") == ["Tier: you set 3, but the text says Tier 1"]
    assert any("Severity" in n for n in oc({"disruption_severity": 1}, "A catastrophic fire destroyed the plant."))
    assert any("Backup" in n for n in oc({"has_backup_supplier": False}, "We have a qualified backup supplier ready."))
    assert any("Backup" in n for n in oc({"has_backup_supplier": True}, "There is no approved backup supplier."))


def test_override_notes_stay_quiet_on_defaults_and_loose_words():
    from src.agents.classifier_agent import override_conflicts as oc
    port = ("A port in Rotterdam has a one-week delay on our Tier-1 pharmaceutical packaging from a European supplier. "
            "We have a qualified second supplier in Belgium and stock for two weeks.")
    mine = {"disruption_severity": 1, "disruption_type": "Port Congestion", "industry": "Pharmaceuticals",
            "supplier_region": "Europe", "has_backup_supplier": True, "supplier_tier": 1}
    assert oc(mine, port) == []                                  # no severity wording -> no severity warning
    assert oc({"has_backup_supplier": False}, "The company began searching for an alternative supplier.") == []
    assert oc({"disruption_type": "Cyber Attack"}, "Ransomware hit our ERP. The export report is late; the warehouse is idle.") == []
    assert oc({"disruption_type": "Natural Disaster"}, "A flood damaged the laboratory of our pharma supplier.") == []
    assert oc({}, "anything at all") == []


def test_analyze_returns_override_notes(client):
    text = "A factory fire has halted the plant of our Tier-2 pharmaceutical supplier in India for four weeks."
    r = client.post("/analyze", json={"query": text, "profile": {"disruption_type": "Natural Disaster"}})
    assert r.status_code == 200 and any("Factory Incident" in n for n in r.json()["override_notes"])
    r = client.post("/analyze", json={"query": text, "profile": {"disruption_type": "Factory Incident"}})
    assert r.status_code == 200 and r.json()["override_notes"] == []


# ---- strategies with no comparable past case must not be described as historical ----
def _ranked(evidence_cases: int) -> list[dict]:
    return [{"response_type": "Alternative Supplier", "rank": 1, "strategy_score": 80, "evidence_cases": evidence_cases,
             "evidence_total": 30, "expected_full_recovery_days": 90.0, "expected_revenue_loss_usd": 1e6,
             "supplier_change_risk": 0.3, "historical": None, "predicted": None}]


def _llm_claiming_history(monkeypatch):
    from src.services import llm_client
    monkeypatch.setattr(llm_client, "complete_json", lambda *a, **k: {
        "rationale": "This reflects the historical use of this approach in similar cases.", "immediate_actions": ["Call suppliers"],
        "recovery_plan": ["Week 1: start"], "risks": ["Delay risk"], "cited_cases": []})


def test_zero_evidence_strategy_is_labelled_and_not_called_historical(monkeypatch):
    from src.services.recommendation import generate_plan
    _llm_claiming_history(monkeypatch)
    plan = generate_plan("test", _ranked(0), [])
    assert "Model estimate only" in plan["evidence_note"]
    assert "historical use" not in plan["rationale"] and "No comparable past case used this strategy" in plan["rationale"]
    assert "no comparable past cases" in plan["guardrail_note"]
    assert "NO comparable past case" in plan["fact_sheet"]


def test_strategy_with_evidence_keeps_its_wording_and_has_no_label(monkeypatch):
    from src.services.recommendation import generate_plan
    _llm_claiming_history(monkeypatch)
    plan = generate_plan("test", _ranked(12), [])
    assert "evidence_note" not in plan and "historical use" in plan["rationale"]


def test_fact_sheet_leads_with_profile_and_past_outcomes():
    from src.services.recommendation import build_fact_sheet
    hist = {"case_count": 40, "median_full_recovery_days": 98.0, "avg_partial_recovery_days": 30.0, "example_cases": []}
    row = {"response_type": "Alternative Supplier", "rank": 1, "strategy_score": 80, "evidence_cases": 40, "evidence_total": 120,
           "expected_full_recovery_days": 90.0, "expected_revenue_loss_usd": 1e6, "supplier_change_risk": 0.3,
           "historical": hist, "predicted": {"predicted_full_recovery_days": 123.4, "predicted_partial_recovery_days": 36.2,
                                             "supplier_change_probability": 0.4, "predicted_revenue_loss_usd": 4.9e6}}
    prof = {"disruption_type": "Cyber Attack", "disruption_severity": 5, "supplier_tier": 1, "industry": "Automotive",
            "supplier_region": "Europe", "has_backup_supplier": False}
    lines = build_fact_sheet([row], [], None, prof).splitlines()
    assert lines[0] == "DISRUPTION PROFILE - Cyber Attack, severity 5, Tier-1 Automotive supplier in Europe, no backup supplier."
    assert lines[1].startswith("PAST OUTCOMES IN 120 COMPARABLE CASES") and "median full recovery 98 days" in lines[1]
    assert lines[2].startswith("CHOSEN STRATEGY")


def test_golden_reference_uses_the_systems_comparison_pool():
    from evaluation import golden_set
    item = golden_set.load()[0]
    ref, e = item["reference_answer"], item["expected"]
    assert f"severity {e['disruption_severity']}" in ref and e["supplier_region"] in ref
    assert "comparable past cases" in ref and "median full recovery" in ref and "Recommended:" in ref
    assert "clear recovery milestones" not in ref                      # filler that no evidence could support
    assert item["acceptable_responses"] and ref.split("Recommended: ")[1].startswith(item["acceptable_responses"][0])


# ---- offline (keyword-rule) classifier ----
def test_rules_read_backup_wording():
    from src.agents.classifier_agent import rule_classify as rc
    assert rc("We already have a qualified second supplier in Thailand.")["has_backup_supplier"] is True
    assert rc("We have a pre-approved second source in Mexico.")["has_backup_supplier"] is True
    assert rc("The manufacturer had no immediate backup supplier.")["has_backup_supplier"] is False
    assert rc("There is no approved backup source.")["has_backup_supplier"] is False
    assert rc("We rely on this supplier alone.")["has_backup_supplier"] is False
    assert rc("The company began searching for an alternative supplier.")["has_backup_supplier"] is None


def test_rules_read_severity_sensibly():
    from src.agents.classifier_agent import rule_classify as rc
    sev = lambda t: rc(t)["estimated_severity"]
    assert sev("A one-week delay. We have enough stock for two weeks.") <= 3        # stock duration is not outage length
    assert sev("Critical components are delayed by a minor strike.") <= 2           # "critical components" is not severity
    assert sev("The port is closed. The supplier is operating normally and no production shutdown is expected.") <= 2
    assert sev("Malware shut down the systems. Impact is moderate.") == 2           # explicit wording beats "shut down"
    assert sev("A catastrophic fire destroyed the plant.") == 5
    assert sev("Ransomware hit our supplier, production halted") >= 4


def test_rules_break_industry_ties_by_first_mention():
    from src.agents.classifier_agent import rule_classify as rc
    assert rc("A delay on our pharmaceutical packaging from a supplier.")["industry"] == "Pharmaceuticals"
    assert rc("An automotive manufacturer lost critical electronic components.")["industry"] == "Automotive"


def test_ambiguity_notes_flag_only_clear_contradictions():
    from src.agents.classifier_agent import ambiguity_notes
    clear = "Ransomware attack has locked the ERP systems of our Tier-2 auto parts supplier in Germany; shipments stopped for 5 days."
    assert ambiguity_notes(clear) == []
    both = "We have a backup supplier but no backup supplier at all, after a ransomware attack."
    assert any("backup supplier" in n for n in ambiguity_notes(both))
    # a value the user set themselves is never second-guessed
    assert ambiguity_notes(both, {"has_backup_supplier": False}) == []


def test_rule_classifier_reads_durations_and_admits_when_it_guesses():
    from src.agents.classifier_agent import rule_classify
    one_day = rule_classify("1 day power outage in a pharmaceutical company")
    assert one_day["estimated_severity"] == 1 and one_day["severity_source"] == "duration"
    assert rule_classify("The factory was shut for three months after the fire")["estimated_severity"] == 5
    assert rule_classify("Port strike for a few hours this morning")["estimated_severity"] == 1
    # explicit wording still wins over a duration, and runway/forecast durations are not the length of the event
    assert rule_classify("Severe outage lasting one day")["severity_source"] == "explicit"
    assert rule_classify("Supplier plant halted; our line can continue for about a week")["severity_source"] != "duration"
    guess = rule_classify("A hurricane hit our plant")
    assert guess["estimated_severity"] == 3 and guess["severity_source"] == "default" and "assumed" in guess["reasoning"]


def test_unstated_severity_is_listed_as_an_assumption():
    from src.agents.classifier_agent import rule_classify
    from src.agents.investigation_agent import investigate
    q = "A hurricane hit our plant"
    inv = investigate(q, rule_classify(q), {}, top_k=5)
    assert any(a.startswith("disruption_severity not stated") for a in inv["assumptions"])
    q = "1 day power outage in a pharmaceutical company"
    assert not any(a.startswith("disruption_severity") for a in investigate(q, rule_classify(q), {}, top_k=5)["assumptions"])


def test_tier_is_read_in_either_word_order():
    from src.agents.classifier_agent import _validated, rule_classify
    for text, tier in [("1 tier pharmaceutical faces power outage", 1), ("Tier 2 supplier fire", 2), ("our tier-3 supplier", 3),
                       ("a second-tier electronics supplier", 2), ("tier one automotive supplier down", 1), ("Port 1 tiered pricing", None)]:
        assert rule_classify(text)["supplier_tier"] == tier, text
    # a model-chosen severity of 3 with no size cue in the text is still a guess, a different value is the model's judgement
    fb = rule_classify("1 tier pharmaceutical faces power outage")
    assert _validated({"estimated_severity": 3}, fb)["severity_source"] == "default"
    assert _validated({"estimated_severity": 2}, fb)["severity_source"] == "llm"


def test_rule_classifier_maps_countries_and_cities_to_the_six_regions():
    from src.agents.classifier_agent import rule_classify
    for place, region in [("Germany", "Europe"), ("Italy", "Europe"), ("Ireland", "Europe"), ("Hong Kong", "Asia-Pacific"), ("Bangladesh", "Asia-Pacific"),
                          ("Mexico", "North America"), ("Chicago", "North America"), ("Ecuador", "South America"), ("Lagos", "Africa/Middle East"),
                          ("Qatar", "Africa/Middle East")]:
        assert rule_classify(f"A factory fire disrupted our supplier in {place}.")["supplier_region"] == region, place
    assert rule_classify("Jordan from procurement says there are delays")["supplier_region"] is None  # a name, not a country
