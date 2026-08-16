"""Vector storage backends (public re-export).

Provides both the synchronous :class:`VectorStorage` and asynchronous
:class:`AsyncVectorStorage` backends, split into ``_sync`` and ``_async``
modules respectively. Kept as a re-export shim so existing import and test
patch paths (``secondbrain.storage.storage.*``) keep resolving.
"""

from secondbrain.config import config
from secondbrain.storage._async import AsyncVectorStorage
from secondbrain.storage._sync import VectorStorage
from secondbrain.utils.connections import ValidatableService

__all__ = ["AsyncVectorStorage", "ValidatableService", "VectorStorage", "config"]
