"""Canonical governed-connector declaration for the optional Twenty boundary."""

from saathi.connectors.gov.models import AuthMode, ConnectorKind, ConnectorManifest


TWENTY_READ_OPERATIONS = (
    "health",
    "list_companies",
    "retrieve_company",
    "list_people",
    "retrieve_person",
    "list_opportunities",
    "retrieve_opportunity",
    "list_tasks",
    "retrieve_task",
    "fetch_object_metadata",
    "fetch_custom_object_schema",
)


def twenty_connector_manifest() -> ConnectorManifest:
    """Return a declaration only; registration never activates connectivity."""
    return ConnectorManifest(
        connector_id="twenty_crm_readonly",
        version="0.1.0",
        kind=ConnectorKind.HTTP,
        auth_mode=AuthMode.FUTURE_SECRET_MANAGER,
        capabilities=TWENTY_READ_OPERATIONS,
        permissions=("crm.read",),
        supported_operations=TWENTY_READ_OPERATIONS,
        allowed_operations=TWENTY_READ_OPERATIONS,
        denied_operations=("create", "update", "delete", "send", "execute"),
        allowed_domains=("127.0.0.1", "localhost", "::1"),
        cloud=False,
        trading=False,
        display_name="Twenty CRM (read-only evaluation)",
        owner="saathi",
        trust_level="LOCAL_SERVICE",
        capability_classes=("READ",),
        side_effect_classes=("READ_ONLY",),
        required_approvals=(),
        secret_references=("TWENTY_API_CREDENTIAL_REFERENCE",),
        rollout_compatible=("OFF", "SHADOW"),
        supported_environments=("local", "dev", "test"),
        description="Optional localhost Twenty adapter; fixture contracts only until live validation.",
        health_policy={"startup_check": "health", "health_check": "health", "fail_closed": True},
        readiness_policy={"readiness_check": "health", "requires_live_validation": True},
    )
