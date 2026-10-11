"""Domain vocabulary taken from the dataset. Used for validation, classification and filtering."""

DISRUPTION_TYPES = ["Port Congestion", "Geopolitical", "Labor Strike", "Natural Disaster", "Cyber Attack", "Factory Incident"]
INDUSTRIES = ["Electronics", "Automotive", "Consumer Goods", "Pharmaceuticals", "Aerospace"]
REGIONS = ["Asia-Pacific", "Europe", "North America", "South America", "Africa/Middle East"]
SUPPLIER_SIZES = ["Small", "Medium", "Large"]
RESPONSE_TYPES = ["Alternative Supplier", "Production Reroute", "Inventory Buffer", "Customer Delay", "Combined Strategy"]
SUPPLIER_TIERS = [1, 2, 3, 4]
SEVERITY_LEVELS = [1, 2, 3, 4, 5]

CATEGORICAL_FEATURES = ["disruption_type", "industry", "supplier_region", "supplier_size"]
NUMERIC_FEATURES = ["supplier_tier", "disruption_severity", "has_backup_supplier"]
TARGETS = {
    "production_impact_pct": "Production impact (%)",
    "revenue_loss_usd": "Revenue loss (USD)",
    "full_recovery_days": "Full recovery (days)",
    "partial_recovery_days": "Partial recovery (days)",
}

# Keyword lexicon used by the rule-based classifier fallback and the off-topic guardrail.
TYPE_KEYWORDS = {
    "Natural Disaster": ["earthquake", "flood", "typhoon", "hurricane", "cyclone", "tsunami", "wildfire", "fire season",
                         "storm", "volcano", "drought", "landslide", "natural disaster", "tornado", "monsoon", "snow"],
    "Cyber Attack": ["cyber", "ransomware", "hack", "malware", "breach", "phishing", "ddos", "it outage",
                     "systems down", "erp", "encrypted", "attack on systems"],
    "Labor Strike": ["strike", "union", "walkout", "labor", "labour", "workers", "industrial action", "protest", "picket"],
    "Port Congestion": ["port", "congestion", "vessel", "container", "shipping", "backlog", "dock", "berth",
                        "freight", "customs", "canal", "harbor", "harbour", "logistics delay"],
    "Geopolitical": ["sanction", "tariff", "war", "export ban", "embargo", "political", "conflict", "border",
                     "trade restriction", "geopolitical", "government", "regulation", "military"],
    "Factory Incident": ["factory", "explosion", "plant fire", "equipment", "machine", "contamination", "recall",
                         "quality", "breakdown", "accident", "power outage", "production line", "plant shutdown"],
}
INDUSTRY_KEYWORDS = {
    "Electronics": ["chip", "semiconductor", "electronic", "pcb", "display", "battery", "circuit", "smartphone", "laptop"],
    "Automotive": ["car", "vehicle", "automotive", "auto parts", "oem", "ev ", "engine", "tyre", "tire", "brake"],
    "Consumer Goods": ["consumer", "retail", "apparel", "textile", "household", "fmcg", "packaging", "food", "toys"],
    "Pharmaceuticals": ["pharma", "drug", "api ", "medicine", "vaccine", "active ingredient", "clinical", "biotech"],
    "Aerospace": ["aerospace", "aircraft", "aviation", "airframe", "turbine", "avionics", "defense", "titanium"],
}
REGION_KEYWORDS = {
    "Asia-Pacific": ["asia", "china", "chinese", "taiwan", "japan", "korea", "vietnam", "india", "thailand",
                     "malaysia", "singapore", "indonesia", "philippines", "australia", "shanghai", "shenzhen"],
    "Europe": ["europe", "germany", "german", "france", "italy", "spain", "uk", "britain", "poland", "netherlands",
               "rotterdam", "hamburg", "eu ", "czech", "sweden"],
    "North America": ["usa", "u.s.", "united states", "america", "canada", "mexico", "texas", "california",
                      "los angeles", "detroit", "us "],
    "South America": ["brazil", "argentina", "chile", "peru", "colombia", "south america", "latin america"],
    "Africa/Middle East": ["africa", "middle east", "uae", "dubai", "saudi", "egypt", "suez", "nigeria", "south africa",
                           "israel", "turkey", "red sea", "kenya", "morocco"],
}
# More places per region for the keyword-rule classifier (the LLM already knows geography). Ambiguous names (Georgia, Jordan, Chad,
# Santos, Lima) are left out on purpose.
for _region, _more in {
    "Europe": ["ireland", "portugal", "belgium", "switzerland", "austria", "romania", "hungary", "finland", "denmark", "norway", "greece",
               "bulgaria", "croatia", "slovakia", "slovenia", "serbia", "ukraine", "russia", "lithuania", "latvia", "estonia", "luxembourg",
               "england", "scotland", "wales", "milan", "frankfurt", "munich", "antwerp", "barcelona", "stuttgart"],
    "Asia-Pacific": ["bangladesh", "pakistan", "sri lanka", "new zealand", "hong kong", "cambodia", "myanmar", "nepal", "mongolia", "taipei",
                     "seoul", "tokyo", "osaka", "mumbai", "chennai", "bangalore", "bangkok", "jakarta", "manila", "hanoi", "ho chi minh",
                     "guangzhou", "beijing", "ningbo", "busan", "kaohsiung", "asian"],
    "North America": ["new york", "chicago", "houston", "long beach", "ohio", "michigan", "ontario", "quebec", "vancouver", "toronto", "monterrey"],
    "South America": ["ecuador", "uruguay", "bolivia", "paraguay", "venezuela", "sao paulo", "buenos aires", "bogota"],
    "Africa/Middle East": ["ghana", "ethiopia", "qatar", "iran", "iraq", "kuwait", "oman", "bahrain", "lebanon", "tunisia", "algeria", "tanzania",
                           "uganda", "angola", "mozambique", "libya", "abu dhabi", "doha", "riyadh", "cairo", "johannesburg", "lagos", "mombasa",
                           "tel aviv", "jeddah", "persian gulf", "hormuz"],
}.items():
    REGION_KEYWORDS[_region] = REGION_KEYWORDS[_region] + [w for w in _more if w not in REGION_KEYWORDS[_region]]

SUPPLY_CHAIN_TERMS = sorted({w for d in (TYPE_KEYWORDS, INDUSTRY_KEYWORDS) for ws in d.values() for w in ws} | {
    "supplier", "supply", "disruption", "production", "manufactur", "shipment", "delivery", "inventory", "recovery",
    "procure", "sourcing", "vendor", "plant", "warehouse", "logistics", "outage", "shortage", "delay", "lead time",
    "revenue", "impact", "severity", "tier", "backup", "parts", "component", "raw material", "operations"})
