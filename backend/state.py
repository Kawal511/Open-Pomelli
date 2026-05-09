from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, TypedDict
from uuid import uuid4


class AgentLog(TypedDict, total=False):
    seq: int
    ts: str
    agent: str
    level: str
    message: str
    latency_ms: int
    extra: Dict[str, Any]


class CampaignContext(TypedDict):
    campaign_id: str
    status: str
    current_node: str
    refinement_count: int
    progress: Dict[str, Any]
    last_error: Dict[str, Any]

    start_payload: Dict[str, Any]

    brand_dna: Dict[str, Any]
    market_brief: Dict[str, Any]
    audience_segments: List[Dict[str, Any]]
    locale_profiles: List[Dict[str, Any]]
    strategy: Dict[str, Any]
    content: Dict[str, Any]
    creative_agent: Dict[str, Any]
    critic_eval: Dict[str, Any]
    keyword_strategy: Dict[str, Any]
    schedule: Dict[str, Any]
    competitor_gaps: Dict[str, Any]
    node_outputs: Dict[str, Dict[str, Any]]

    completed_nodes: Annotated[List[str], operator.add]
    agent_logs: Annotated[List[AgentLog], operator.add]


def initial_state(start_payload: Dict[str, Any]) -> CampaignContext:
    target_markets = start_payload.get("target_markets", [])
    return CampaignContext(
        campaign_id=str(uuid4()),
        status="queued",
        current_node="START",
        refinement_count=0,
        progress={
            "completed": 0,
            "total": 11,
            "target_markets": len(target_markets),
            "percent": 0,
        },
        last_error={},
        start_payload=start_payload,
        brand_dna={},
        market_brief={},
        audience_segments=[],
        locale_profiles=[],
        strategy={},
        content={},
        creative_agent={},
        critic_eval={},
        keyword_strategy={},
        schedule={},
        competitor_gaps={},
        node_outputs={},
        completed_nodes=[],
        agent_logs=[],
    )
