"""The fairness invariant: no plan ever gates model-provider access."""
import models
import plan


def test_every_provider_allowed_on_every_plan():
    for p in ("free", "pro", "team", "enterprise", "unknown-defaults-to-free"):
        for provider in models.PROVIDERS:
            assert plan.provider_allowed(p, provider) is True


def test_free_includes_all_providers_and_core_features():
    ent = plan.entitlements("free")
    assert ent["all_model_providers"] is True
    assert ent["byo_api_keys"] is True
    assert ent["price_usd_month"] == 0
    # core, local, self-hostable capabilities are all free
    for feature in ("real_repo_mode", "draft_verify_ship", "multi_agent",
                    "repo_indexing", "computer_control", "api_server_self_host"):
        assert plan.feature_enabled("free", feature)


def test_paid_tiers_only_add_hosted_conveniences():
    free, pro, team = (plan.entitlements(x) for x in ("free", "pro", "team"))
    # things free does NOT include but paid does are hosted/collab only
    assert not free["hosted_memory_sync"] and pro["hosted_memory_sync"]
    assert not free["team_library"] and team["team_library"]
    # but everything free had, paid keeps (never removes access)
    for k, v in free.items():
        if v is True:
            assert pro.get(k) is True and team.get(k) is True


def test_summary_states_fairness():
    assert "never gated" in plan.summary("free")
