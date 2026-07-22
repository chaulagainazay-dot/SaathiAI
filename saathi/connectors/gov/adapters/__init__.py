"""M27 governed connector adapters."""
from saathi.connectors.gov.adapters.browser import BrowserAdapter
from saathi.connectors.gov.adapters.http import HttpAdapter
from saathi.connectors.gov.adapters.local_tool import LocalToolAdapter
from saathi.connectors.gov.adapters.mcp import McpAdapter

__all__ = ["BrowserAdapter", "HttpAdapter", "LocalToolAdapter", "McpAdapter"]
