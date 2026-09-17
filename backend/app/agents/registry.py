from dataclasses import dataclass
from typing import Any, Protocol

from app.schemas.orchestration import TaskSpec, Refusal
from app.constants.failures import FailureCode
from app.constants.intents import Intent
from app.constants.routing import Modality
from app.agents.router import SceneFacts
from app.services.query.ontology import canonicalize_target

@dataclass(frozen=True)
class CapabilityEvaluation:
    is_valid: bool
    refusal: Refusal | None = None
    fallback_intent: Intent | None = None

class Capability(Protocol):
    @property
    def id(self) -> str: ...
    
    @property
    def supported_intents(self) -> list[Intent]: ...
    
    @property
    def output_capabilities(self) -> list[str]: ...
    
    def evaluate(self, task: TaskSpec, facts: SceneFacts) -> CapabilityEvaluation: ...
    
    def build_step(self, task: TaskSpec) -> dict[str, Any]: ...


class DotaDetectorCapability:
    @property
    def id(self) -> str: return "dota-detector"
    
    @property
    def supported_intents(self) -> list[Intent]:
        return [Intent.DETECT, Intent.GROUND]
        
    @property
    def output_capabilities(self) -> list[str]:
        return ["count", "bounding_boxes", "qualitative_presence"]

    def evaluate(self, task: TaskSpec, facts: SceneFacts) -> CapabilityEvaluation:
        if task.intent not in self.supported_intents:
            return CapabilityEvaluation(is_valid=False)

        # Validate ontology
        from app.constants.detection import DOTA_CLASS_NAMES
        target = canonicalize_target(task.target) or ""
        if target not in DOTA_CLASS_NAMES:
            return CapabilityEvaluation(
                is_valid=False,
                refusal=Refusal(
                    code=FailureCode.MODEL_DOMAIN_MISMATCH,
                    target=target,
                    reason=f"No detector in the fleet precisely detects '{target}'. Supported: {', '.join(DOTA_CLASS_NAMES)}."
                ),
                fallback_intent=Intent.SCENE_VQA
            )
            
        # Validate resolution
        if facts.ground_sample_distance is not None:
            from app.constants.routing import MIN_OBJECT_PIXELS
            from app.services.query.entities import required_ground_sample_distance
            needed = required_ground_sample_distance(target)
            if facts.ground_sample_distance > needed:
                return CapabilityEvaluation(
                    is_valid=False,
                    refusal=Refusal(
                        code=FailureCode.RESOLUTION_FAILURE,
                        target=target,
                        reason=f"A {target} spans fewer than {MIN_OBJECT_PIXELS} pixels at {facts.ground_sample_distance:g} m per pixel; detecting one needs {needed:.2g} m or finer.",
                        gsd=facts.ground_sample_distance,
                        required_max_gsd=needed
                    )
                )

        return CapabilityEvaluation(is_valid=True)

    def build_step(self, task: TaskSpec) -> dict[str, Any]:
        target = canonicalize_target(task.target) or ""
        return {
            "id": task.task_id,
            "query": task.question or f"Detect {target}",
            "intent": task.intent.value,
            "tool": "dota-detector",
            "graph": "detect",
            "method": "agent",
            "rule": None,
            "objects": [target] if target else [],
            "unknown_objects": [],
            "spectral_phrase": None,
            "wants_count": "count" in task.requested_outputs,
            "wants_location": "bounding_boxes" in task.requested_outputs
        }


class VLMCapability:
    @property
    def id(self) -> str: return "vlm"
    
    @property
    def supported_intents(self) -> list[Intent]:
        return [Intent.SCENE_VQA, Intent.CHANGE_VQA]
        
    @property
    def output_capabilities(self) -> list[str]:
        return ["qualitative_presence"]
        
    def evaluate(self, task: TaskSpec, facts: SceneFacts) -> CapabilityEvaluation:
        if task.intent not in self.supported_intents:
            return CapabilityEvaluation(is_valid=False)
            
        # VLM provides qualitative answers. Cannot provide strict counts.
        if "count" in task.requested_outputs:
            return CapabilityEvaluation(
                is_valid=False,
                refusal=Refusal(
                    code=FailureCode.SCIENTIFIC_INVALID,
                    target=task.target,
                    reason="The VLM can say whether it is present, but its counts are not measurements."
                )
            )
            
        if task.intent == Intent.CHANGE_VQA and facts.image_count < 2:
            return CapabilityEvaluation(
                is_valid=False,
                refusal=Refusal(
                    code=FailureCode.MISSING_INPUT,
                    target=None,
                    reason="CHANGE_VQA requires two acquisitions."
                )
            )
            
        return CapabilityEvaluation(is_valid=True)

    def build_step(self, task: TaskSpec) -> dict[str, Any]:
        return {
            "id": task.task_id,
            "query": task.question or (f"Are there {task.target}?" if task.target else "Describe the scene."),
            "intent": task.intent.value,
            "tool": "vlm",
            "graph": "vqa",
            "method": "agent",
            "rule": None,
            "objects": [task.target] if task.target else [],
            "unknown_objects": [],
            "spectral_phrase": None,
            "wants_count": False,
            "wants_location": False
        }


class ChangeDetectorCapability:
    @property
    def id(self) -> str: return "changeformer"
    
    @property
    def supported_intents(self) -> list[Intent]:
        return [Intent.CHANGE_DETECT]
        
    @property
    def output_capabilities(self) -> list[str]:
        return ["mask", "area", "change_magnitude"]
        
    def evaluate(self, task: TaskSpec, facts: SceneFacts) -> CapabilityEvaluation:
        if task.intent not in self.supported_intents:
            return CapabilityEvaluation(is_valid=False)
            
        if facts.image_count < 2:
            return CapabilityEvaluation(
                is_valid=False,
                refusal=Refusal(
                    code=FailureCode.MISSING_INPUT,
                    target=None,
                    reason="CHANGE_DETECT requires two acquisitions."
                )
            )
            
        return CapabilityEvaluation(is_valid=True)

    def build_step(self, task: TaskSpec) -> dict[str, Any]:
        return {
            "id": task.task_id,
            "query": task.question or "Detect changes.",
            "intent": task.intent.value,
            "tool": "changeformer",
            "graph": "change",
            "method": "agent",
            "rule": None,
            "objects": [],
            "unknown_objects": [],
            "spectral_phrase": None,
            "wants_count": False,
            "wants_location": False
        }

class SegformerCapability:
    @property
    def id(self) -> str: return "segformer"
    
    @property
    def supported_intents(self) -> list[Intent]:
        return [Intent.SEGMENT]
        
    @property
    def output_capabilities(self) -> list[str]:
        return ["mask", "area"]
        
    def evaluate(self, task: TaskSpec, facts: SceneFacts) -> CapabilityEvaluation:
        if task.intent not in self.supported_intents:
            return CapabilityEvaluation(is_valid=False)
        return CapabilityEvaluation(is_valid=True)

    def build_step(self, task: TaskSpec) -> dict[str, Any]:
        target = canonicalize_target(task.target) or ""
        return {
            "id": task.task_id,
            "query": task.question or f"Segment {target}",
            "intent": task.intent.value,
            "tool": "segformer",
            "graph": "segment",
            "method": "agent",
            "rule": None,
            "objects": [target] if target else [],
            "unknown_objects": [],
            "spectral_phrase": None,
            "wants_count": False,
            "wants_location": False
        }

class EvidenceRecallCapability:
    @property
    def id(self) -> str: return "evidence_recall"
    
    @property
    def supported_intents(self) -> list[Intent]:
        return [Intent.EVIDENCE_RECALL]
        
    @property
    def output_capabilities(self) -> list[str]:
        return ["count", "bounding_boxes", "mask", "area", "qualitative_presence", "change_magnitude"]
        
    def evaluate(self, task: TaskSpec, facts: SceneFacts) -> CapabilityEvaluation:
        if task.intent not in self.supported_intents:
            return CapabilityEvaluation(is_valid=False)
        return CapabilityEvaluation(is_valid=True)

    def build_step(self, task: TaskSpec) -> dict[str, Any]:
        return {
            "id": task.task_id,
            "query": task.question or "Recall evidence.",
            "intent": task.intent.value,
            "tool": None,
            "graph": None,
            "method": "agent",
            "rule": None,
            "objects": [],
            "unknown_objects": [],
            "spectral_phrase": None,
            "wants_count": False,
            "wants_location": False
        }


class CapabilityRegistry:
    def __init__(self):
        self._capabilities = [
            DotaDetectorCapability(),
            VLMCapability(),
            ChangeDetectorCapability(),
            SegformerCapability(),
            EvidenceRecallCapability()
        ]
        
    def check_feasibility(self, task: TaskSpec, facts: SceneFacts) -> tuple[Capability | None, Refusal | None]:
        """
        Feasibility Engine: Evaluates a TaskSpec against the registry.
        Returns the resolved Capability and a Refusal if it cannot be executed.
        """
        best_refusal = None
        for cap in self._capabilities:
            if task.intent in cap.supported_intents:
                eval_result = cap.evaluate(task, facts)
                if eval_result.is_valid:
                    # Check requested outputs
                    unsupported = set(task.requested_outputs) - set(cap.output_capabilities)
                    if unsupported:
                        best_refusal = Refusal(
                            code=FailureCode.SCIENTIFIC_INVALID,
                            target=task.target,
                            reason=f"Capability {cap.id} does not support outputs: {', '.join(unsupported)}."
                        )
                        continue
                    return cap, None
                elif eval_result.fallback_intent:
                    # Deterministic downgrade/fallback handling
                    # E.g. DOTA failed on ontology, suggests VQA fallback
                    task_copy = task.model_copy(update={"intent": eval_result.fallback_intent})
                    return self.check_feasibility(task_copy, facts)
                elif eval_result.refusal:
                    best_refusal = eval_result.refusal

        # If no capability matched or all failed
        if best_refusal is None:
            best_refusal = Refusal(
                code=FailureCode.UNSUPPORTED_INTENT,
                target=task.target,
                reason=f"No capability registered for intent {task.intent.value}."
            )
        return None, best_refusal
