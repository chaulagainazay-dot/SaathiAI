"""System integration test: ToolIntent → ExecutionGateway → Adapters."""

import asyncio
import logging
from datetime import datetime

from saathi.execution.toolintent import ToolIntent
from saathi.execution.gateway import ExecutionContext
from saathi.execution.integration import execute
from saathi.execution.queue.memory import MemoryQueue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_video_generation_flow():
    """Test complete video generation flow."""
    logger.info("=" * 60)
    logger.info("TEST: Video Generation Flow")
    logger.info("=" * 60)

    intent = ToolIntent(
        intent_id="test-video-001",
        operation="video-generation",
        business_unit="baadar",
        actor_id="user:123",
        parameters={
            "prompt": "Create a 30-second Mr. Yeti explaining IELTS listening tips",
            "duration_sec": 30,
            "style": "animated",
        },
        metadata={
            "urgency": "normal",
            "budget": 2.0,
            "quality_tier": "broadcast",
            "character_type": "yeti",
        },
    )

    context = ExecutionContext(
        actor_id="user:123",
        business_unit="baadar",
        timestamp=datetime.utcnow(),
        current_time=datetime.utcnow(),
    )

    result = await execute(intent, context)
    logger.info(f"Result: {result.status}")
    logger.info(f"Cost: ${result.cost_usd}")
    logger.info(f"Duration: {result.duration_sec}s")
    assert result.status.value in ("success", "partial"), f"Expected success/partial, got {result.status}"


async def test_local_llm_flow():
    """Test complete local LLM inference flow."""
    logger.info("=" * 60)
    logger.info("TEST: Local LLM Inference Flow")
    logger.info("=" * 60)

    intent = ToolIntent(
        intent_id="test-llm-001",
        operation="local-llm-inference",
        business_unit="pielts",
        actor_id="user:456",
        parameters={
            "prompt": "Explain IELTS Writing Task 2 in 100 words",
            "model": "auto-select",
        },
        metadata={
            "urgency": "low",
            "data_sensitivity": "confidential",  # Force local
            "max_latency_sec": 30,
        },
    )

    context = ExecutionContext(
        actor_id="user:456",
        business_unit="pielts",
        timestamp=datetime.utcnow(),
        current_time=datetime.utcnow(),
    )

    result = await execute(intent, context)
    logger.info(f"Result: {result.status}")
    logger.info(f"Cost: ${result.cost_usd}")
    assert result.status.value in ("success", "partial"), f"Expected success/partial, got {result.status}"


async def main():
    """Run all integration tests."""
    logger.info("STARTING SAATHIOS INTEGRATION TESTS")
    logger.info("=" * 60)

    try:
        await test_video_generation_flow()
        await test_local_llm_flow()
        logger.info("=" * 60)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ TEST FAILED: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
