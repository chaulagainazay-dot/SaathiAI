"""Connector drivers — the ONLY place SDK / provider details live.

Each driver wraps one external service behind the uniform Connector contract.
Adding an integration = add a driver here + its Manifest. Nothing above this
package imports an SDK.
"""
from .telegram import TelegramConnector
from .github import GitHubConnector
from .n8n import N8nConnector
from .browser import BrowserConnector
from .youtube import YouTubeConnector
from .filesystem import FilesystemConnector
from .human_publish import HumanPublishConnector
from .code_memory import CodeMemoryConnector

__all__ = ["TelegramConnector", "GitHubConnector", "N8nConnector",
           "BrowserConnector", "YouTubeConnector", "FilesystemConnector",
           "HumanPublishConnector", "CodeMemoryConnector"]
