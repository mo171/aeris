from app.lib.responses import CamelCaseModel

class AssistantSuggestion(CamelCaseModel):
    id: str
    text: str
    pillar: str

class SuggestionsResponse(CamelCaseModel):
    suggestions: list[AssistantSuggestion]
