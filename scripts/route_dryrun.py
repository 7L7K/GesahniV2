#!/usr/bin/env python3
"""CLI tool to test GesahniV2 model routing decisions in dry-run mode.

Usage:
    uv run python scripts/route_dryrun.py --scenario <name> [--stream] [--privacy] [--tokens N]

Scenarios:
    simple_prompt: Short "Hello" prompt
    heavy_sql: Long text + "sql", ~3000 tokens
    attachments_2: 2+ files present
    override_llama: model_override="llama3:latest"
    long_context: RAG tokens > 6000, intent=analysis
    embed_req: task_type="embed"
"""

import argparse
import asyncio
import os
import sys

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.router.entrypoint import route_prompt, RoutingDecision


def build_scenario_payload(
    scenario: str, stream: bool = True, privacy: bool = False, tokens: int = 0
) -> dict:
    """Build test payload for the given scenario."""
    base_payload = {
        "stream": stream,
        "privacy_mode": privacy,
    }

    if scenario == "simple_prompt":
        base_payload.update(
            {
                "prompt": "Hello, how are you today?",
                "task_type": "chat",
            }
        )
    elif scenario == "heavy_sql":
        sql_prompt = (
            """
        I have a complex SQL query that involves multiple joins and aggregations.
        The query needs to analyze sales data across different time periods and
        customer segments. It should include window functions, CTEs, and proper
        indexing considerations. Please help me optimize this query for performance
        and provide the best practices for execution.
        """
            * 10
        )  # Make it long
        base_payload.update(
            {
                "prompt": sql_prompt,
                "task_type": "chat",
            }
        )
    elif scenario == "attachments_2":
        base_payload.update(
            {
                "prompt": "Please analyze these documents and provide a summary.",
                "task_type": "chat",
                "attachments_count": 2,
            }
        )
    elif scenario == "override_llama":
        base_payload.update(
            {
                "prompt": "Tell me a joke.",
                "model_override": "llama3:latest",
                "task_type": "chat",
            }
        )
    elif scenario == "long_context":
        base_payload.update(
            {
                "prompt": "Please analyze this research paper and provide insights.",
                "task_type": "chat",
                "intent_hint": "analysis",
                "rag_tokens": 7000,  # > 6000 threshold
            }
        )
    elif scenario == "embed_req":
        base_payload.update(
            {
                "prompt": "Convert this text to embeddings",
                "task_type": "embed",
            }
        )
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    if tokens > 0:
        # Override token count if specified
        pass  # Would need to modify payload to force token count

    return base_payload


def print_tsv_header():
    """Print TSV header."""
    print(
        "scenario\tmodel_id\tprovider\tstream\treason\tfallback_chain\trules_triggered"
    )


def print_decision_tsv(scenario: str, decision: RoutingDecision):
    """Print routing decision as TSV line."""
    fallback_str = ";".join(decision.fallback_chain) if decision.fallback_chain else ""
    rules_str = ";".join(decision.rules_triggered) if decision.rules_triggered else ""
    print(
        f"{scenario}\t{decision.model_id}\t{decision.provider}\t{decision.stream}\t{decision.reason}\t{fallback_str}\t{rules_str}"
    )


async def main():
    parser = argparse.ArgumentParser(description="Test GesahniV2 routing decisions")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=[
            "simple_prompt",
            "heavy_sql",
            "attachments_2",
            "override_llama",
            "long_context",
            "embed_req",
        ],
        help="Test scenario to run",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        default=True,
        help="Enable streaming (default: True)",
    )
    parser.add_argument(
        "--privacy", action="store_true", default=False, help="Enable privacy mode"
    )
    parser.add_argument("--tokens", type=int, default=0, help="Override token count")

    args = parser.parse_args()

    # Set dry-run environment
    os.environ["DRY_RUN"] = "true"
    os.environ["DEBUG_MODEL_ROUTING"] = "true"

    # Build payload for scenario
    payload = build_scenario_payload(
        args.scenario, stream=args.stream, privacy=args.privacy, tokens=args.tokens
    )

    # Get routing decision
    decision = await route_prompt(payload, dry_run=True)

    if not isinstance(decision, RoutingDecision):
        print(f"ERROR: Expected RoutingDecision, got {type(decision)}", file=sys.stderr)
        sys.exit(1)

    # Print TSV output
    print_tsv_header()
    print_decision_tsv(args.scenario, decision)


if __name__ == "__main__":
    asyncio.run(main())
