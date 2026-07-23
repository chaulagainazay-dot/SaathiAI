# M49.4 Residual Legacy Census

Generated from live `saathi.tools.registry._HANDLERS` + `legacy_policy` classification.

## Summary

- Handler count: **120**
- Outside explicit policy sets: **0**
- UNKNOWN classifications: **0**
- Legacy state: **`LEGACY_RUNTIME_BOUNDED`**

### By closure decision

| Closure decision | Count |
|---|---|
| `CANONICAL_WRAPPER` | 11 |
| `DEFERRED_DISABLED` | 47 |
| `PROHIBITED` | 3 |
| `RETAIN_BOUNDED_WITH_REASON` | 59 |

## Full inventory

| handler | disposition | closure_decision | runtime_reachable | agent_reachable | canonical_equivalent |
|---|---|---|---|---|---|
| `ab_ai_chat` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_batch` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_click` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_close` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_eval` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_fill` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_find_text` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_get_text` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_get_url` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_goto` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_open` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_press` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_screenshot` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_snapshot` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ab_status` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `add_event` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `add_reminder` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `applescript` | PROHIBITED | PROHIBITED | False | False |  |
| `ask_document` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `bilibili_search` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `canteen_query` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `cheap_ask` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `cheap_proxy_status` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `check_animated_video` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `check_email` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.connector.gmail.search_messages |
| `check_messages` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `clean_prose` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `connect_facebook_instagram` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `content_strategy_30day` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `crypto_prices` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `deep_plan` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `deploy_ielts_site` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `dm_sales_converter` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `draft_social_content` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `engagement_booster` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `english_log_mistake` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `english_progress` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `exchange_rate` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `find_community_questions` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `get_mobile_link` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `github_repo` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `hashtag_seo_system` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `list_blueprints` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.list_blueprints |
| `list_projects` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.list_projects |
| `list_reminders` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.list_reminders |
| `list_social_connections` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.list_social_connections |
| `look_at_screen` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `mac_close_app` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `mac_open_app` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `mac_run_shortcut` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `mac_type_text` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `make_animated_video` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `make_blog_post` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `make_content` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `make_daily_kit` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `make_flow_prompts` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `make_quote_image` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `make_quote_kit` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `make_quote_video` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `make_talking_yeti` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `make_video` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `manage_tasks` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.list_open_tasks |
| `ml_add_subscriber` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ml_create_campaign` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ml_create_group` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `ml_get_automation` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `ml_get_subscriber` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `ml_list_automations` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `ml_list_campaigns` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `ml_list_groups` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `ml_list_subscribers` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `ml_stats` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `monthly_analytics_review` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `motivational_quote` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `my_files` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.my_files_list |
| `nepali_progress` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `performance_report` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.performance_report |
| `plan_project_work` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `post_social_content` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `post_to_all_socials` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `profile_optimizer` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `project_edit_file` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `project_overview` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `project_run` | PROHIBITED | PROHIBITED | False | False |  |
| `publish_blog` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `publish_to_youtube` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `queue_video` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `reach_doctor` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `read_mac_file` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `read_project_file` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `read_webpage` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `record_feedback` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `register_project` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `remember_fact` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `render_hyperframes_video` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `research` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `rss_feed` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `run_shell` | PROHIBITED | PROHIBITED | False | False |  |
| `score_prose` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `search_mac_files` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `search_project` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `self_improve` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `self_status` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `send_email` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.connector.gmail.send_message |
| `send_telegram` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `send_video_to_phone` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `social_dashboard` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `stage_draft` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `system_health` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.system_health |
| `teach_nepali` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `todays_content` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `todays_events` | MIGRATED_CANONICAL | CANONICAL_WRAPPER | True | True | m49.todays_events |
| `trigger_blueprint` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `trigger_n8n_workflow` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `viral_hook_generator` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `web_search` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `what_learned` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `write_file` | DEFERRED_AND_DISABLED | DEFERRED_DISABLED | False | False |  |
| `youtube_info` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |
| `youtube_subtitles` | LEGACY_BOUNDED | RETAIN_BOUNDED_WITH_REASON | True | True |  |

## Classification rules (exactly one per handler)

| Class | Meaning |
|---|---|
| `CANONICAL_WRAPPER` | Mapped to ExecutionGateway via LEGACY_NAME_MAP |
| `DEFERRED_DISABLED` | Inventored deferred domain; execute_tool blocks |
| `PROHIBITED` | Freeform shell / financial prohibited |
| `RETAIN_BOUNDED_WITH_REASON` | Temporary LEGACY_BOUNDED after governance |

No `UNKNOWN` remains.

## Callers

| Caller | Path |
|---|---|
| Agent (`saathi.agent`) | `execute_tool` (legacy dispatcher + gateway for mapped) |
| Agent runtime gateway_exec | `ExecutionGateway.execute_registered_tool` for m49.* |
| API / CLI audit | discovery-only for audit tools |
| Compatibility | `try_canonical_legacy_tool` → gateway |

## Authority / side-effect note

LEGACY_BOUNDED handlers still use pre-M49 governance (`ActionRequest` gate) rather than
manifest-owned authority. That is the primary reason `LEGACY_RUNTIME_ELIMINATED` is **not** claimed.
