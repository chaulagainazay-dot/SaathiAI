"""Business event sources — each business converts its NATIVE events into Evidence.
Businesses only emit events; these handlers are the only code that understands
each business's semantics. Add a business = add a handler + a route.
"""
from saathi.businesses import pielts, hcg, cafeteria, travel, studio

HANDLERS = {"pielts": pielts.handle, "hcg": hcg.handle, "cafeteria": cafeteria.handle,
            "travel": travel.handle, "ai_studio": studio.handle}

__all__ = ["HANDLERS", "pielts", "hcg", "cafeteria", "travel", "studio"]
