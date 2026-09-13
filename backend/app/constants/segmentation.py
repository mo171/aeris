"""What the land-cover segmenter predicts, and the words an operator uses for each class - fixed sets, not code.

what  : `LOVEDA_CLASS_NAMES` in the checkpoint's label order, `LANDCOVER_SYNONYMS` from an operator's word
        to a class, `SEGMENTATION_IGNORE_LABEL`, and the floor below which a class is listed but not drawn.
where : `app/models/segmentation.py` checks the checkpoint's `id2label` against the names; the S13 node
        and `services/segmentation/classes.py` resolve a question's words to classes; S15 reads the floor.
how   : LoveDA's seven land covers (Wang et al. 2021) plus the `Ignore` label its loss skipped, in the order
        the checkpoint states them - the index *is* the class id in the retained class map. A synonym
        table rather than fuzzy matching, so "buildings" resolves to `Building` and "the built-up area"
        does too, but "building site" does not resolve to anything: an unknown word is a stated refusal.
"""

from typing import Final

LOVEDA_CLASS_NAMES: Final[tuple[str, ...]] = (
    "Ignore", "Background", "Building", "Road", "Water", "Barren", "Forest", "Agricultural",
)
SEGMENTATION_IGNORE_LABEL: Final[int] = 0

# Operator's word -> LoveDA class. Whole words, singular and plural, as `OBJECT_SYNONYMS` does for the detector.
LANDCOVER_SYNONYMS: Final[dict[str, str]] = {
    "building": "Building", "buildings": "Building", "house": "Building", "houses": "Building", "built-up": "Building",
    "built up": "Building", "urban": "Building", "structures": "Building", "rooftops": "Building", "footprints": "Building",
    "building footprints": "Building", "settlement": "Building", "settlements": "Building",
    "road": "Road", "roads": "Road", "street": "Road", "streets": "Road", "highway": "Road", "highways": "Road",
    "water": "Water", "water bodies": "Water", "lake": "Water", "lakes": "Water", "river": "Water", "rivers": "Water",
    "pond": "Water", "ponds": "Water", "reservoir": "Water", "reservoirs": "Water",
    "barren": "Barren", "bare": "Barren", "bare soil": "Barren", "bare ground": "Barren", "barren land": "Barren",
    "forest": "Forest", "forests": "Forest", "trees": "Forest", "tree cover": "Forest", "woodland": "Forest", "wood": "Forest",
    "agricultural": "Agricultural", "agriculture": "Agricultural", "farmland": "Agricultural", "farm": "Agricultural",
    "farms": "Agricultural", "crops": "Agricultural", "cropland": "Agricultural", "fields": "Agricultural", "field": "Agricultural",
}

# A class whose share of observed ground is below this is reported in the land-cover table and not localised
# as regions when no class was named: half a percent of a Sentinel-2 subset is a few hundred pixels of
# something the model was unsure about, and drawing it as evidence would give it a weight it did not earn.
SEGMENTATION_MINIMUM_CLASS_FRACTION: Final[float] = 0.005
