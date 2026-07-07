"""Plan entitlements - the fair, BYO-key billing model.

Core fairness rule, enforced in code: a plan NEVER gates which model provider
you can use. If you bring your own API key (or run Ollama locally), every
provider works on the FREE plan - you're already paying the provider directly.
Paid tiers only add hosted conveniences (sync, collaboration, compliance);
they never unlock model access, because model access is never locked.

No payment processing lives here - this is the entitlement map the app reads.
"""

# Everything a self-hosting FREE user gets. Paid tiers ADD to this; they never
# remove or gate provider access.
FREE = {
    "all_model_providers": True,     # any provider, with your own key / local Ollama
    "byo_api_keys": True,
    "self_host": True,
    "memory_backends": ["chroma", "lite"],
    "web_search_byo_key": True,      # any search provider with your own key
    "real_repo_mode": True,
    "draft_verify_ship": True,
    "computer_control": True,
    "multi_agent": True,
    "repo_indexing": True,
    "skills_import_export": True,
    "checkpoints": True,
    "api_server_self_host": True,
    "mobile_apps": True,
    "price_usd_month": 0,
}

PLANS = {
    "free": {**FREE, "hosted_memory_sync": False, "team_library": False,
             "rbac_audit": False, "sso": False, "managed_search_credits": False,
             "container_sandbox_managed": False, "sla_support": False},
    # Paid tiers only ADD hosted conveniences.
    "pro": {**FREE, "price_usd_month": 20, "hosted_memory_sync": True,
            "checkpoint_cloud_backup": True, "managed_search_credits": True,
            "priority_routing": True},
    "team": {**FREE, "price_usd_month": 50, "hosted_memory_sync": True,
             "team_library": True, "rbac_audit": True, "sso": True,
             "usage_dashboard": True},
    "enterprise": {**FREE, "price_usd_month": None, "container_sandbox_managed": True,
                   "vpc_self_host": True, "compliance_soc2": True, "sla_support": True,
                   "team_library": True, "rbac_audit": True, "sso": True},
}


def entitlements(plan: str = "free") -> dict:
    return PLANS.get((plan or "free").lower(), PLANS["free"])


def provider_allowed(plan: str, provider: str) -> bool:
    """Always True. Provider access is a fairness invariant, not a plan feature -
    you pay the model provider, so Corvus never charges to reach one."""
    return True


def feature_enabled(plan: str, feature: str) -> bool:
    return bool(entitlements(plan).get(feature, False))


def summary(plan: str = "free") -> str:
    ent = entitlements(plan)
    price = ent.get("price_usd_month")
    price_s = "free" if price == 0 else ("custom" if price is None else f"${price}/mo")
    on = sorted(k for k, v in ent.items() if v is True)
    lines = [f"Plan: {plan} ({price_s})",
             "Fairness: any model provider works on every plan with your own key "
             "(or local Ollama). Provider access is never gated.",
             "Included:"]
    lines += [f"  - {k}" for k in on]
    return "\n".join(lines)
