import asyncio
import time
from pathlib import Path
from pprint import pprint

# Old Orchestration
from app.agents.router import route, SceneFacts
from app.models.encoder import load_encoder
from app.services.query.bank import embed_bank, load_fresh
from app.constants.intents import Intent

# New Orchestration
from app.agents.harness.agent import run_harness
from app.agents.harness.state import AgentState
from app.lib.llm.chat_model import build_chat_model

async def test_comparison():
    print("Setting up models and databases...")
    encoder = await load_encoder()
    bank = await embed_bank(encoder, await load_fresh())
    llm = build_chat_model()
    
    test_cases = [
        {
            "name": "Test A - Valid Detection",
            "query": "Detect ships and calculate their count.",
            "facts": {"image_count": 1, "modalities": ["optical"], "ground_sample_distance": 0.5, "is_registered": True}
        },
        {
            "name": "Test B - Ontology Failure (Fallback to VLM)",
            "query": "Detect trees.",
            "facts": {"image_count": 1, "modalities": ["optical"], "ground_sample_distance": 0.5, "is_registered": True}
        },
        {
            "name": "Test C - Resolution Failure",
            "query": "Detect cars.",
            "facts": {"image_count": 1, "modalities": ["optical"], "ground_sample_distance": 10.0, "is_registered": True}
        },
        {
            "name": "Test D - Compound Valid",
            "query": "Compare the two dates, tell me whether built-up area increased, and calculate the increase.",
            "facts": {"image_count": 2, "modalities": ["optical"], "ground_sample_distance": 0.5, "is_registered": True}
        },
        {
            "name": "Test E - Dependency",
            "query": "Find changed buildings and calculate their total area.",
            "facts": {"image_count": 2, "modalities": ["optical"], "ground_sample_distance": 0.5, "is_registered": True}
        }
    ]

    print("\n================ ORCHESTRATION COMPARISON ================\n")

    for case in test_cases:
        print(f"--- {case['name']} ---")
        print(f"Query: {case['query']}")
        
        facts_dict = case["facts"]
        old_facts = SceneFacts(
            image_count=facts_dict["image_count"],
            ground_sample_distance=facts_dict["ground_sample_distance"]
        )
        new_facts = SceneFacts(
            image_count=facts_dict["image_count"],
            ground_sample_distance=facts_dict["ground_sample_distance"]
        )

        # ---------------- OLD ROUTER ----------------
        t0 = time.time()
        try:
            old_decision = await route(case['query'], encoder=encoder, bank=bank, facts=old_facts)
            old_time = time.time() - t0
            old_status = "REFUSED" if old_decision.refusal else "ROUTED"
            old_details = old_decision.refusal if old_decision.refusal else f"Intent: {old_decision.intent.value} | Tool: {old_decision.tool.value if old_decision.tool else 'None'}"
        except Exception as e:
            old_time = time.time() - t0
            old_status = "ERROR"
            old_details = str(e)
            
        print(f"\n[OLD ROUTER]")
        print(f"Time: {old_time:.3f}s")
        print(f"Status: {old_status}")
        print(f"Details: {old_details}")
        
        # ---------------- NEW HARNESS ----------------
        t0 = time.time()
        try:
            new_answer = await run_harness(case['query'], facts=new_facts, model=llm)
            new_time = time.time() - t0
            new_status = "COMPLETED"
            # Mock execution: if no refusals, generate mock claims based on intent
            if not refusals:
                for task in state.tasks:
                    if task.intent.value == "DETECT":
                        state.observations.append(AgentObservation(
                            task_id=task.task_id,
                            claim={"type": "count", "value": 14, "target": task.target},
                            refusal=None
                        ))
                    elif task.intent.value == "SEGMENT":
                        state.observations.append(AgentObservation(
                            task_id=task.task_id,
                            claim={"type": "area", "value": "1.2 sq km", "target": task.target},
                            refusal=None
                        ))
            new_details = new_answer
        except Exception as e:
            new_time = time.time() - t0
            new_status = "ERROR"
            new_details = str(e)

        print(f"\n[NEW AGENT HARNESS]")
        print(f"Time: {new_time:.3f}s")
        print(f"Status: {new_status}")
        print(f"Synthesis: {new_details}")
        print("----------------------------------------------------------\n")

if __name__ == "__main__":
    asyncio.run(test_comparison())
