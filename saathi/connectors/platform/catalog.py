"""M15 capability catalog — provider-neutral capability IDs.

Capabilities are stable even when provider adapters change. Each capability
declares a default risk class so tools inherit a safe floor.
"""
from __future__ import annotations

from saathi.connectors.platform.models import RiskClass

# capability_id -> (category, default_risk)
CAPABILITIES: dict[str, tuple[str, RiskClass]] = {
    # communication
    "search_email": ("communication", RiskClass.EXTERNAL_READ),
    "read_email": ("communication", RiskClass.EXTERNAL_READ),
    "draft_email": ("communication", RiskClass.REVERSIBLE_MUTATION),
    "send_email": ("communication", RiskClass.EXTERNAL_SIDE_EFFECT),
    "reply_email": ("communication", RiskClass.EXTERNAL_SIDE_EFFECT),
    "send_message": ("communication", RiskClass.EXTERNAL_SIDE_EFFECT),
    "send_notification": ("communication", RiskClass.EXTERNAL_SIDE_EFFECT),
    "post_channel_message": ("communication", RiskClass.EXTERNAL_SIDE_EFFECT),
    # calendar + contacts
    "list_calendar_events": ("calendar", RiskClass.EXTERNAL_READ),
    "create_calendar_event": ("calendar", RiskClass.EXTERNAL_SIDE_EFFECT),
    "update_calendar_event": ("calendar", RiskClass.EXTERNAL_SIDE_EFFECT),
    "cancel_calendar_event": ("calendar", RiskClass.EXTERNAL_SIDE_EFFECT),
    "search_contacts": ("contacts", RiskClass.EXTERNAL_READ),
    # code + git
    "inspect_repository": ("git", RiskClass.EXTERNAL_READ),
    "read_file": ("git", RiskClass.LOCAL_READ),
    "write_file": ("git", RiskClass.REVERSIBLE_MUTATION),
    "create_branch": ("git", RiskClass.REVERSIBLE_MUTATION),
    "create_commit": ("git", RiskClass.REVERSIBLE_MUTATION),
    "push_branch": ("git", RiskClass.EXTERNAL_SIDE_EFFECT),
    "open_pull_request": ("git", RiskClass.EXTERNAL_SIDE_EFFECT),
    "list_issues": ("git", RiskClass.EXTERNAL_READ),
    "create_issue": ("git", RiskClass.EXTERNAL_SIDE_EFFECT),
    "inspect_ci": ("git", RiskClass.EXTERNAL_READ),
    "trigger_ci": ("git", RiskClass.EXTERNAL_SIDE_EFFECT),
    # browser
    "open_url": ("browser", RiskClass.EXTERNAL_READ),
    "extract_page": ("browser", RiskClass.EXTERNAL_READ),
    "click_element": ("browser", RiskClass.REVERSIBLE_MUTATION),
    "fill_form": ("browser", RiskClass.REVERSIBLE_MUTATION),
    "download_file": ("browser", RiskClass.EXTERNAL_READ),
    "capture_screenshot": ("browser", RiskClass.EXTERNAL_READ),
    "run_browser_workflow": ("browser", RiskClass.EXTERNAL_SIDE_EFFECT),
    # local system
    "run_read_only_command": ("local", RiskClass.LOCAL_READ),
    "run_local_command": ("local", RiskClass.REVERSIBLE_MUTATION),
    "inspect_process": ("local", RiskClass.LOCAL_READ),
    "inspect_disk": ("local", RiskClass.LOCAL_READ),
    "read_local_file": ("local", RiskClass.LOCAL_READ),
    "write_local_file": ("local", RiskClass.REVERSIBLE_MUTATION),
    # databases
    "inspect_schema": ("database", RiskClass.EXTERNAL_READ),
    "query_database": ("database", RiskClass.EXTERNAL_READ),
    "insert_record": ("database", RiskClass.EXTERNAL_SIDE_EFFECT),
    "update_record": ("database", RiskClass.EXTERNAL_SIDE_EFFECT),
    "delete_record": ("database", RiskClass.EXTERNAL_SIDE_EFFECT),
    "run_migration": ("database", RiskClass.HIGH_IMPACT),
    # deployment
    "inspect_deployment": ("deployment", RiskClass.EXTERNAL_READ),
    "create_preview_deployment": ("deployment", RiskClass.EXTERNAL_SIDE_EFFECT),
    "deploy_to_staging": ("deployment", RiskClass.EXTERNAL_SIDE_EFFECT),
    "deploy_to_production": ("deployment", RiskClass.HIGH_IMPACT),
    "rollback_deployment": ("deployment", RiskClass.HIGH_IMPACT),
    "inspect_logs": ("deployment", RiskClass.EXTERNAL_READ),
    # content
    "upload_video": ("content", RiskClass.EXTERNAL_SIDE_EFFECT),
    "publish_video": ("content", RiskClass.EXTERNAL_SIDE_EFFECT),
    "publish_post": ("content", RiskClass.EXTERNAL_SIDE_EFFECT),
    "schedule_post": ("content", RiskClass.EXTERNAL_SIDE_EFFECT),
    "upload_image": ("content", RiskClass.EXTERNAL_SIDE_EFFECT),
    "fetch_analytics": ("content", RiskClass.EXTERNAL_READ),
    "reply_to_comment": ("content", RiskClass.EXTERNAL_SIDE_EFFECT),
    # ai
    "run_llm_inference": ("ai", RiskClass.EXTERNAL_READ),
    "create_embedding": ("ai", RiskClass.EXTERNAL_READ),
    "generate_image": ("ai", RiskClass.EXTERNAL_SIDE_EFFECT),
    "generate_video": ("ai", RiskClass.EXTERNAL_SIDE_EFFECT),
    "synthesize_speech": ("ai", RiskClass.EXTERNAL_READ),
    "transcribe_audio": ("ai", RiskClass.EXTERNAL_READ),
    # storage
    "upload_file": ("storage", RiskClass.EXTERNAL_SIDE_EFFECT),
    "list_files": ("storage", RiskClass.EXTERNAL_READ),
    "move_file": ("storage", RiskClass.REVERSIBLE_MUTATION),
    "delete_file": ("storage", RiskClass.EXTERNAL_SIDE_EFFECT),
    "create_folder": ("storage", RiskClass.REVERSIBLE_MUTATION),
    # automation
    "create_workflow": ("automation", RiskClass.REVERSIBLE_MUTATION),
    "trigger_workflow": ("automation", RiskClass.EXTERNAL_SIDE_EFFECT),
    "pause_workflow": ("automation", RiskClass.REVERSIBLE_MUTATION),
    "inspect_workflow": ("automation", RiskClass.EXTERNAL_READ),
    "receive_webhook": ("automation", RiskClass.LOCAL_READ),
}


def capability_risk(capability_id: str) -> RiskClass:
    return CAPABILITIES.get(capability_id, ("unknown", RiskClass.HIGH_IMPACT))[1]


def capability_category(capability_id: str) -> str:
    return CAPABILITIES.get(capability_id, ("unknown", RiskClass.HIGH_IMPACT))[0]


def all_capabilities() -> list[dict]:
    return [{"capability_id": cid, "category": cat, "default_risk": int(risk)}
            for cid, (cat, risk) in sorted(CAPABILITIES.items())]
