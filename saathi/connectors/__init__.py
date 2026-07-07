"""Universal Account & Connector layer — every Mission/Director reaches external
services through here, never a provider SDK directly. Provider-agnostic, secrets
encrypted at rest, every action emits an event into Evidence + Timeline.
"""
from saathi.connectors.catalog import catalog, provider_info, capabilities_for, PROVIDERS, CAPABILITIES
from saathi.connectors.accounts import AccountStore, default_store
from saathi.connectors.manager import execute, register_adapter, provider_health

__all__ = ["catalog", "provider_info", "capabilities_for", "PROVIDERS", "CAPABILITIES",
           "AccountStore", "default_store", "execute", "register_adapter", "provider_health"]
