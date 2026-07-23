"""M49.3 legacy saathi.tools policy — migrate, wrap, defer, or prohibit.

Every legacy tool name is classified. Deferred and prohibited tools must not
remain executable through saathi.tools.execute_tool. Canonical tools route
via ExecutionGateway. Unknown names are rejected (no generic fallback).
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class LegacyDisposition(str, Enum):
    MIGRATED_CANONICAL = "MIGRATED_CANONICAL"
    WRAPPED_CANONICAL = "WRAPPED_CANONICAL"
    LEGACY_BOUNDED = "LEGACY_BOUNDED"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"
    DEFERRED_AND_DISABLED = "DEFERRED_AND_DISABLED"
    DEPRECATED_AND_BLOCKED = "DEPRECATED_AND_BLOCKED"
    PROHIBITED = "PROHIBITED"
    TEST_ONLY = "TEST_ONLY"


# Maps legacy tool name → canonical tool_id (gateway path)
CANONICAL_LEGACY_MAP: dict[str, str] = {
    "system_health": "m49.system_health",
    "my_files": "m49.my_files_list",
    "manage_tasks": "m49.list_open_tasks",
    "list_projects": "m49.list_projects",
    "list_reminders": "m49.list_reminders",
    "list_social_connections": "m49.list_social_connections",
    "list_blueprints": "m49.list_blueprints",
    "performance_report": "m49.performance_report",
    "todays_events": "m49.todays_events",
    "check_email": "m49.connector.gmail.search_messages",
    "send_email": "m49.connector.gmail.send_message",
}

# Freeform shell / arbitrary command — never executable
FREEFORM_SHELL_TOOLS: frozenset[str] = frozenset(
    {
        "run_shell",
        "project_run",
        "applescript",
    }
)

# Financial execution / live trading — always prohibited
PROHIBITED_TOOLS: frozenset[str] = frozenset(
    {
        "place_order",
        "cancel_order",
        "live_trade",
        "withdraw_funds",
        "enable_leverage",
        "broker_execute",
        "exchange_execute",
    }
)

# Domains deferred out of runtime (not executable; discovery schemas may remain)
DEFERRED_RUNTIME_TOOLS: frozenset[str] = frozenset(
    {
        # browser agent
        "ab_open",
        "ab_close",
        "ab_goto",
        "ab_click",
        "ab_fill",
        "ab_press",
        "ab_get_text",
        "ab_get_url",
        "ab_find_text",
        "ab_screenshot",
        "ab_snapshot",
        "ab_status",
        "ab_eval",
        "ab_batch",
        "ab_ai_chat",
        # privileged Mac control
        "mac_open_app",
        "mac_close_app",
        "mac_run_shortcut",
        "mac_type_text",
        "look_at_screen",
        "check_messages",
        "search_mac_files",
        "read_mac_file",
        "write_file",
        # deployment / live publish
        "deploy_ielts_site",
        "publish_to_youtube",
        "publish_blog",
        "queue_video",
        "post_social_content",
        "post_to_all_socials",
        "connect_facebook_instagram",
        "send_telegram",
        "send_video_to_phone",
        "trigger_n8n_workflow",
        "trigger_blueprint",
        # live calendar mutation
        "add_event",
        "add_reminder",
        # engineering project mutations (shell-adjacent)
        "project_edit_file",
        "register_project",
        # mailerlite / campaign mutations
        "ml_create_campaign",
        "ml_create_group",
        "ml_add_subscriber",
        # media pipelines requiring external providers
        "make_animated_video",
        "make_talking_yeti",
        "make_video",
        "render_hyperframes_video",
        "make_flow_prompts",
    }
)

# Safe-ish local tools still allowed via bounded legacy path (documented temporary)
LEGACY_BOUNDED_TOOLS: frozenset[str] = frozenset(
    {
        "canteen_query",
        "draft_social_content",
        "stage_draft",
        "english_log_mistake",
        "english_progress",
        "nepali_progress",
        "teach_nepali",
        "what_learned",
        "remember_fact",
        "project_overview",
        "read_project_file",
        "search_project",
        "plan_project_work",
        "research",
        "web_search",
        "read_webpage",
        "rss_feed",
        "youtube_info",
        "youtube_subtitles",
        "github_repo",
        "crypto_prices",
        "exchange_rate",
        "bilibili_search",
        "motivational_quote",
        "make_quote_image",
        "make_quote_kit",
        "make_quote_video",
        "make_content",
        "make_blog_post",
        "make_daily_kit",
        "todays_content",
        "content_strategy_30day",
        "viral_hook_generator",
        "hashtag_seo_system",
        "engagement_booster",
        "profile_optimizer",
        "dm_sales_converter",
        "monthly_analytics_review",
        "find_community_questions",
        "ask_document",
        "self_improve",
        "self_status",
        "record_feedback",
        "deep_plan",
        "clean_prose",
        "score_prose",
        "cheap_ask",
        "cheap_proxy_status",
        "social_dashboard",
        "ml_list_subscribers",
        "ml_list_campaigns",
        "ml_list_groups",
        "ml_list_automations",
        "ml_get_subscriber",
        "ml_get_automation",
        "ml_stats",
        "reach_doctor",
        "get_mobile_link",
        "check_animated_video",
    }
)


def classify_legacy_tool(name: str) -> LegacyDisposition:
    if not name:
        return LegacyDisposition.PROHIBITED
    if name in PROHIBITED_TOOLS:
        return LegacyDisposition.PROHIBITED
    if name in FREEFORM_SHELL_TOOLS:
        return LegacyDisposition.PROHIBITED
    if name in CANONICAL_LEGACY_MAP:
        return LegacyDisposition.MIGRATED_CANONICAL
    if name in DEFERRED_RUNTIME_TOOLS:
        return LegacyDisposition.DEFERRED_AND_DISABLED
    if name in LEGACY_BOUNDED_TOOLS:
        return LegacyDisposition.LEGACY_BOUNDED
    # Residual handlers (including test-registered tools): bounded legacy path
    # after governance. Unknown *names* without handlers are rejected at the
    # dispatcher before classification is consulted for execution.
    return LegacyDisposition.LEGACY_BOUNDED


def is_runtime_executable(name: str) -> bool:
    d = classify_legacy_tool(name)
    return d in (
        LegacyDisposition.MIGRATED_CANONICAL,
        LegacyDisposition.WRAPPED_CANONICAL,
        LegacyDisposition.LEGACY_BOUNDED,
    )


def block_payload(name: str, disposition: LegacyDisposition | None = None) -> dict[str, Any]:
    d = disposition or classify_legacy_tool(name)
    if d == LegacyDisposition.PROHIBITED or name in FREEFORM_SHELL_TOOLS:
        return {
            "error": "freeform_shell_blocked"
            if name in FREEFORM_SHELL_TOOLS
            else "tool_prohibited",
            "blocked": True,
            "disposition": d.value,
            "tool": name,
            "message": (
                "M49.3: freeform shell / arbitrary command execution is prohibited. "
                "Use allowlisted command manifests via ExecutionGateway "
                "(tool_id=m49.allowlisted_command)."
                if name in FREEFORM_SHELL_TOOLS
                else f"M49.3: tool '{name}' is prohibited at runtime."
            ),
            "outcome_class": "PROHIBITED",
            "canonical_path": "ExecutionGateway.execute_registered_tool",
        }
    if d == LegacyDisposition.DEFERRED_AND_DISABLED:
        return {
            "error": "tool_deferred_disabled",
            "blocked": True,
            "disposition": d.value,
            "tool": name,
            "message": (
                f"M49.3: tool '{name}' is deferred and not runtime-executable. "
                "It is not callable through freeform shell or generic connector paths."
            ),
            "outcome_class": "BLOCKED",
        }
    return {
        "error": "tool_blocked",
        "blocked": True,
        "disposition": d.value,
        "tool": name,
        "message": f"M49.3: tool '{name}' is not executable via legacy runtime ({d.value}).",
        "outcome_class": "BLOCKED",
    }


def policy_summary() -> dict[str, Any]:
    return {
        "canonical_mapped": sorted(CANONICAL_LEGACY_MAP.keys()),
        "freeform_shell_blocked": sorted(FREEFORM_SHELL_TOOLS),
        "prohibited": sorted(PROHIBITED_TOOLS),
        "deferred_disabled": sorted(DEFERRED_RUNTIME_TOOLS),
        "legacy_bounded": sorted(LEGACY_BOUNDED_TOOLS),
        "counts": {
            "canonical": len(CANONICAL_LEGACY_MAP),
            "freeform_shell": len(FREEFORM_SHELL_TOOLS),
            "prohibited": len(PROHIBITED_TOOLS),
            "deferred": len(DEFERRED_RUNTIME_TOOLS),
            "legacy_bounded": len(LEGACY_BOUNDED_TOOLS),
        },
    }
