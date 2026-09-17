from typing import Optional

def canonicalize_target(raw_target: str | None) -> str | None:
    """
    Normalizes user language (e.g., 'ships', 'vessels') into a canonical ontology entity ('ship').
    This ensures the Feasibility Engine checks scientific validity rather than failing on linguistics.
    """
    if not raw_target:
        return None
        
    target = raw_target.lower().strip()
    
    synonyms = {
        "ships": "ship",
        "vessels": "ship",
        "vessel": "ship",
        "boats": "ship",
        "boat": "ship",
        
        "planes": "plane",
        "airplanes": "plane",
        "aircraft": "plane",
        "aircrafts": "plane",
        
        "cars": "small vehicle",
        "car": "small vehicle",
        "vehicles": "small vehicle",
        "small vehicles": "small vehicle",
        
        "trucks": "large vehicle",
        "truck": "large vehicle",
        "large vehicles": "large vehicle",
        
        "trees": "tree",
        
        "buildings": "building",
        "houses": "building",
        "structures": "building"
    }
    
    return synonyms.get(target, target)
