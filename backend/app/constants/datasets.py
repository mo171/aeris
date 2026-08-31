"""The one place that says which datasets this project uses, what each is for, how it is laid out on disk, and what its licence permits.

what  : `DatasetId`, `DatasetSplit`, `LayoutKind`, `DatasetLayout`, `DatasetRecord`, and
        `DATASET_CATALOGUE` - one record per dataset, transcribed from the PDF's Table 5 (pp.21-24).
where : Read by `services/datasets/` (the loader reads `layout`, the catalogue reader reads `directory`),
        by `aeris dataset list|show|fetch`, and by every phase from 1.6 that trains or evaluates on one.
how   : Three things are recorded per dataset, and each answers a question that is expensive to answer late.

        **What it unlocks, and when.** `unlocked_in` names the sub-phase that first needs it. Read down the
        catalogue and it is the acquisition schedule: nothing here is downloaded speculatively, because
        several of these are tens of gigabytes and a laptop is the development machine.

        **What its licence permits** - `constants/licences.py`. The roadmap's gate is about sequence:
        recorded *before* training, not after. Every dataset whose terms nobody has read carries
        `Licence.UNVERIFIED`, which denies everything, plus the URL where the real terms are and the
        specific thing to check. A test fails if a dataset is marked ready for training while unverified.

        **How it is laid out on disk.** `layout` is what makes "every one loads through a single loader"
        true rather than aspirational: the loader in `services/datasets/loader.py` reads this declaration
        instead of carrying a branch per dataset. Six layout shapes cover the whole table, which is the
        useful finding - the datasets differ enormously in content and barely at all in structure.

        **What is deliberately not here.** No label parsing. A LEVIR-CD mask, a DOTA oriented bounding box
        and an RSVQA question are read by the phase that has a model to feed them to (1.6, 1.7), not by
        1.1. What 1.1 owes is acquisition, licensing, cataloguing and *enumeration* - and a loader that
        enumerates is a loader that can verify a dataset is complete, which is the thing worth having now.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from app.constants.licences import Licence


class DatasetId(StrEnum):
    """Every dataset this project uses. The id is also its directory name under the datasets root."""

    # Imagery we acquire ourselves, rather than a published benchmark. The AOI scenes every pipeline phase
    # from 1.2 to 1.5 actually runs on.
    SENTINEL2_L2A = "sentinel2-l2a"
    SENTINEL1_GRD = "sentinel1-grd"

    # Change detection - 1.6, and the change gate.
    LEVIR_CD = "levir-cd"
    S2LOOKING = "s2looking"
    SECOND = "second"
    OSCD = "oscd"

    # Object detection - 1.6.
    DOTA = "dota"
    DIOR = "dior"

    # Land-cover segmentation - 1.6.
    LOVEDA = "loveda"
    OPEN_EARTH_MAP = "open-earth-map"

    # Vision-language - 1.7 and the 1.14 benchmark.
    RSVQA_LR = "rsvqa-lr"
    RSVQA_HR = "rsvqa-hr"
    VRSBENCH = "vrsbench"

    # Grounding - 1.6.
    DIOR_RSVG = "dior-rsvg"
    RRSIS_D = "rrsis-d"

    # Optical-SAR pairing - 1.11.
    SEN12MS = "sen12ms"
    BIGEARTHNET_MM = "bigearthnet-mm"

    # Sanity checks and fast demos - used throughout, and the smallest thing here by two orders of
    # magnitude, which is why it is the one the loader tests run against for real.
    EUROSAT = "eurosat"


class DatasetSplit(StrEnum):
    """The splits a dataset publishes. Not every dataset has all of them."""

    TRAIN = "train"
    VALIDATION = "val"
    TEST = "test"

    # For imagery we acquired ourselves and benchmarks published as one undivided set.
    ALL = "all"


class LayoutKind(StrEnum):
    """The shape a dataset takes on disk.

    Six shapes cover the whole of the PDF's Table 5, which is the point of enumerating them: the datasets
    differ enormously in what they contain and barely at all in how they are arranged, so one loader can
    read all of them from a declaration rather than a branch per dataset.
    """

    # `<split>/A/x.png`, `<split>/B/x.png`, `<split>/label/x.png` - the bi-temporal change layout.
    PAIRED_MASK = "paired-mask"

    # `<split>/images/x.png`, `<split>/masks/x.png` - segmentation.
    IMAGE_MASK = "image-mask"

    # `<split>/images/x.png`, `<split>/labelTxt/x.txt` - detection and grounding, annotation per image.
    IMAGE_ANNOTATION = "image-annotation"

    # `<class>/<class>_1.jpg` - the class is the directory. Scene classification.
    CLASS_FOLDERS = "class-folders"

    # `images/x.tif` plus one JSON sidecar holding every question. VQA and captioning.
    IMAGE_SIDECAR = "image-sidecar"

    # One directory per scene, holding its bands and metadata. What `aeris dataset fetch` writes.
    SCENE_DIRECTORIES = "scene-directories"


@dataclass(frozen=True, slots=True)
class DatasetLayout:
    """Where a loader finds the files of one dataset.

    Declarative rather than a function per dataset, so that adding a dataset is an entry in this file and
    no new code. The failure this prevents is the ordinary one: eighteen bespoke loaders, of which three
    handle a missing split differently and nobody notices until an evaluation silently runs on 800 samples
    instead of 1,024.
    """

    kind: LayoutKind

    # Split -> the directory under the dataset root holding it. A dataset published undivided maps
    # `DatasetSplit.ALL` to `"."`.
    split_directories: dict[DatasetSplit, str]

    # Where the images live inside a split directory. Two entries for a bi-temporal dataset - the pair is
    # positional, and `("A", "B")` means A is T1, which is the convention every change dataset here uses.
    image_directories: tuple[str, ...] = ("images",)

    # Masks or per-image annotations, where the layout has a directory for them.
    label_directory: str | None = None

    # One file holding the labels for a whole split - the VQA sidecar.
    label_file: str | None = None

    image_suffixes: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    """One dataset: what it is, what it unlocks, what its licence permits, and how to get it."""

    dataset_id: DatasetId
    title: str

    # Straight from the PDF's Table 5 (pp.21-24), so the catalogue and the design document agree.
    task: str
    sensor: str
    resolution: str
    scale: str

    # The sub-phase that first needs it. Nothing is acquired before the phase that uses it, because several
    # of these are tens of gigabytes and the development machine is a laptop.
    unlocked_in: str

    licence: Licence

    # Where the real terms are published. Present even for a verified licence, because "verified" means
    # someone read this page and it is the thing they would need to read again.
    licence_url: str

    # False until a human has actually read `licence_url`. `Licence.UNVERIFIED` denies everything, so the
    # combination that matters - unverified *and* used for training - is what the catalogue test forbids.
    licence_verified: bool

    # How to get it. Several of these are behind a registration form or a Google Drive link and cannot be
    # fetched programmatically; for those this is the instruction the CLI prints instead of pretending.
    source_url: str
    acquisition: str

    layout: DatasetLayout

    # Approximate download size, for the operator deciding what to fetch tonight. A string because the
    # published figures are approximate and unit-mixed, and inventing precision here would be false.
    approximate_size: str

    # What went wrong, or is surprising, when this dataset is actually used. Grows as each is acquired -
    # the roadmap asks for a notebook per dataset that "records its quirks", and this is where the
    # one-line version of each quirk lives so the loader's caller sees it without opening a notebook.
    quirks: tuple[str, ...] = field(default_factory=tuple)


# The catalogue. Ordered by the phase that unlocks each entry, so reading it top to bottom is the
# acquisition schedule.
DATASET_CATALOGUE: Final[dict[DatasetId, DatasetRecord]] = {
    DatasetId.SENTINEL2_L2A: DatasetRecord(
        dataset_id=DatasetId.SENTINEL2_L2A,
        title="Sentinel-2 L2A (surface reflectance)",
        task="the imagery every pipeline phase actually runs on",
        sensor="Sentinel-2 MSI",
        resolution="10-60 m",
        scale="acquired per AOI",
        unlocked_in="1.2",
        licence=Licence.COPERNICUS_SENTINEL,
        licence_url="https://sentinels.copernicus.eu/web/sentinel/terms-conditions",
        licence_verified=True,
        source_url="https://planetarycomputer.microsoft.com/api/stac/v1",
        acquisition="stac",
        layout=DatasetLayout(
            kind=LayoutKind.SCENE_DIRECTORIES,
            split_directories={DatasetSplit.ALL: "."},
            image_directories=(".",),
            image_suffixes=(".tif", ".tiff"),
        ),
        approximate_size="~230 MB per band; ~1.2 GB for the default five assets",
        quirks=(
            "L2A is surface reflectance and already atmospherically corrected - L1C is not, and mixing "
            "the two in one temporal pair produces a change map of the atmosphere.",
            "Band resolutions differ within one scene: B02/03/04/08 are 10 m, the red edge and SWIR bands "
            "are 20 m, B01/09/10 are 60 m. Any index combining across those needs resampling first.",
            "Reflectance is scaled by 10000 and offset by -1000 from processing baseline 04.00 onwards. "
            "MEASURED over a real scene (notebooks/02_data_exploration/01_sentinel2_l2a.ipynb): forgetting "
            "the offset moves the vegetated fraction from 75.1% to 61.4% - a 13.7 point error, mean "
            "|dNDVI| 0.185. Both maps look like NDVI maps, which is exactly why this is dangerous.",
            "MEASURED: one 10 m band of a full L2A tile is ~230 MB as a COG, not the ~100 MB the "
            "published figures suggest. Two bands is already half a gigabyte, so `--asset` is how a "
            "fetch stays affordable - B04 and B08 alone are enough for NDVI.",
        ),
    ),
    DatasetId.SENTINEL1_GRD: DatasetRecord(
        dataset_id=DatasetId.SENTINEL1_GRD,
        title="Sentinel-1 GRD (radiometrically terrain corrected)",
        task="the SAR half of every cross-modal run",
        sensor="Sentinel-1 C-band SAR",
        resolution="10 m",
        scale="acquired per AOI",
        unlocked_in="1.3",
        licence=Licence.COPERNICUS_SENTINEL,
        licence_url="https://sentinels.copernicus.eu/web/sentinel/terms-conditions",
        licence_verified=True,
        source_url="https://planetarycomputer.microsoft.com/api/stac/v1",
        acquisition="stac",
        layout=DatasetLayout(
            kind=LayoutKind.SCENE_DIRECTORIES,
            split_directories={DatasetSplit.ALL: "."},
            image_directories=(".",),
            image_suffixes=(".tif", ".tiff"),
        ),
        approximate_size="~800 MB per polarisation",
        quirks=(
            "Backscatter is a power ratio, not a reflectance. It is read in dB, and averaging in dB "
            "rather than in linear power is one of the standard ways to get a wrong number.",
            "Ascending and descending passes see different geometry. Comparing across them is a change "
            "map of the look angle.",
        ),
    ),
    DatasetId.EUROSAT: DatasetRecord(
        dataset_id=DatasetId.EUROSAT,
        title="EuroSAT",
        task="scene classification",
        sensor="Sentinel-2",
        resolution="10 m",
        scale="27,000 images, 10 classes",
        unlocked_in="1.1",
        licence=Licence.MIT,
        licence_url="https://github.com/phelber/EuroSAT",
        licence_verified=False,
        source_url="https://madm.dfki.de/files/sentinel/EuroSAT.zip",
        acquisition="download",
        layout=DatasetLayout(
            kind=LayoutKind.CLASS_FOLDERS,
            split_directories={DatasetSplit.ALL: "2750"},
            image_directories=(".",),
            image_suffixes=(".jpg",),
        ),
        approximate_size="~90 MB",
        quirks=(
            "The RGB release is 3-band JPEG, not the 13-band multispectral one. Anything computing an "
            "index needs the MS variant instead, which is a different download.",
            "Images are 64x64 - large enough for a classifier, far too small for anything this project "
            "does with a scene. It is here for sanity checks and fast demos, and for nothing else.",
        ),
    ),
    DatasetId.LEVIR_CD: DatasetRecord(
        dataset_id=DatasetId.LEVIR_CD,
        title="LEVIR-CD",
        task="binary building change detection",
        sensor="Google Earth VHR",
        resolution="0.5 m",
        scale="637 image pairs with building change masks",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://chenhao.in/LEVIR/",
        licence_verified=False,
        source_url="https://chenhao.in/LEVIR/",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.PAIRED_MASK,
            split_directories={
                DatasetSplit.TRAIN: "train",
                DatasetSplit.VALIDATION: "val",
                DatasetSplit.TEST: "test",
            },
            image_directories=("A", "B"),
            label_directory="label",
            image_suffixes=(".png",),
        ),
        approximate_size="~2 GB",
        quirks=(
            "The change class is a small fraction of pixels. Accuracy is meaningless here; the metric is "
            "F1 or IoU on the change class alone, which is what the PDF's evaluation section specifies.",
            "1024x1024 tiles - most published results crop to 256, and a model compared against them "
            "without the same cropping is not being compared against them.",
        ),
    ),
    DatasetId.S2LOOKING: DatasetRecord(
        dataset_id=DatasetId.S2LOOKING,
        title="S2Looking",
        task="building change detection, off-nadir",
        sensor="VHR side-looking",
        resolution="0.5-0.8 m",
        scale="5,000 image pairs",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://github.com/S2Looking/Dataset",
        licence_verified=False,
        source_url="https://github.com/S2Looking/Dataset",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.PAIRED_MASK,
            split_directories={
                DatasetSplit.TRAIN: "train",
                DatasetSplit.VALIDATION: "val",
                DatasetSplit.TEST: "test",
            },
            image_directories=("Image1", "Image2"),
            label_directory="label",
            image_suffixes=(".png",),
        ),
        approximate_size="~10 GB",
        quirks=(
            "Deliberately off-nadir, which is the point of it: a model that only ever saw LEVIR-CD's "
            "near-nadir imagery reports building change where the parallax moved a roof.",
        ),
    ),
    DatasetId.SECOND: DatasetRecord(
        dataset_id=DatasetId.SECOND,
        title="SECOND",
        task="semantic change detection",
        sensor="aerial",
        resolution="0.5-3 m",
        scale="4,662 image pairs, 6 land-cover classes",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://captain-whu.github.io/SCD/",
        licence_verified=False,
        source_url="https://captain-whu.github.io/SCD/",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.PAIRED_MASK,
            split_directories={DatasetSplit.TRAIN: "train", DatasetSplit.TEST: "test"},
            image_directories=("im1", "im2"),
            label_directory="label1",
            image_suffixes=(".png",),
        ),
        approximate_size="~3 GB",
        quirks=(
            "Two label directories, label1 and label2 - the semantic class before and after. Reading only "
            "one turns semantic change into binary change without any error.",
        ),
    ),
    DatasetId.OSCD: DatasetRecord(
        dataset_id=DatasetId.OSCD,
        title="OSCD (Onera Satellite Change Detection)",
        task="binary change detection at Sentinel-2 scale",
        sensor="Sentinel-2",
        resolution="10 m",
        scale="24 city pairs",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://rcdaudt.github.io/oscd/",
        licence_verified=False,
        source_url="https://rcdaudt.github.io/oscd/",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.PAIRED_MASK,
            split_directories={DatasetSplit.TRAIN: "train", DatasetSplit.TEST: "test"},
            image_directories=("imgs_1", "imgs_2"),
            label_directory="labels",
            image_suffixes=(".tif", ".png"),
        ),
        approximate_size="~1 GB",
        quirks=(
            "The only change dataset here at the resolution AERIS actually operates at. A specialist "
            "trained solely on 0.5 m VHR and demonstrated on 10 m Sentinel-2 is being asked to do "
            "something it was never shown - which is exactly the scale gap the PDF flags.",
        ),
    ),
    DatasetId.DOTA: DatasetRecord(
        dataset_id=DatasetId.DOTA,
        title="DOTA v2",
        task="oriented object detection",
        sensor="aerial",
        resolution="various",
        scale="~2,800 images, 15+ classes",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://captain-whu.github.io/DOTA/",
        licence_verified=False,
        source_url="https://captain-whu.github.io/DOTA/",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_ANNOTATION,
            split_directories={DatasetSplit.TRAIN: "train", DatasetSplit.VALIDATION: "val"},
            image_directories=("images",),
            label_directory="labelTxt",
            image_suffixes=(".png",),
        ),
        approximate_size="~20 GB",
        quirks=(
            "Boxes are oriented - four corner points, not x/y/w/h. A detector reading them as axis-aligned "
            "produces plausible-looking boxes that are wrong for every rotated object, which in aerial "
            "imagery is most of them.",
            "Images are very large and are tiled before training; the tiling scheme is part of the "
            "published result and must be recorded with any number this project quotes.",
        ),
    ),
    DatasetId.DIOR: DatasetRecord(
        dataset_id=DatasetId.DIOR,
        title="DIOR",
        task="object detection",
        sensor="VHR optical",
        resolution="0.5-30 m",
        scale="23,463 images, 20 classes",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://gcheng-nwpu.github.io/",
        licence_verified=False,
        source_url="https://gcheng-nwpu.github.io/",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_ANNOTATION,
            split_directories={
                DatasetSplit.TRAIN: "trainval",
                DatasetSplit.TEST: "test",
            },
            image_directories=("JPEGImages",),
            label_directory="Annotations",
            image_suffixes=(".jpg",),
        ),
        approximate_size="~7 GB",
        quirks=("Pascal VOC XML annotations, axis-aligned - the opposite convention from DOTA's.",),
    ),
    DatasetId.LOVEDA: DatasetRecord(
        dataset_id=DatasetId.LOVEDA,
        title="LoveDA",
        task="land-cover segmentation with a domain shift",
        sensor="VHR optical",
        resolution="0.3 m",
        scale="5,987 images, 7 classes",
        unlocked_in="1.6",
        licence=Licence.CC_BY_NC_SA_4_0,
        licence_url="https://github.com/Junjue-Wang/LoveDA",
        licence_verified=False,
        source_url="https://zenodo.org/records/5706578",
        acquisition="download",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_MASK,
            split_directories={
                DatasetSplit.TRAIN: "Train",
                DatasetSplit.VALIDATION: "Val",
                DatasetSplit.TEST: "Test",
            },
            image_directories=("images_png",),
            label_directory="masks_png",
            image_suffixes=(".png",),
        ),
        approximate_size="~2 GB",
        quirks=(
            "Urban and rural are separate domains inside each split, and the dataset exists to measure "
            "the gap between them. Pooling them reports a number that hides the thing being measured.",
        ),
    ),
    DatasetId.OPEN_EARTH_MAP: DatasetRecord(
        dataset_id=DatasetId.OPEN_EARTH_MAP,
        title="OpenEarthMap",
        task="global land-cover segmentation",
        sensor="VHR optical",
        resolution="0.25-0.6 m",
        scale="5,000 images, 8 classes",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://open-earth-map.org/",
        licence_verified=False,
        source_url="https://open-earth-map.org/",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_MASK,
            split_directories={DatasetSplit.TRAIN: "train", DatasetSplit.VALIDATION: "val"},
            image_directories=("images",),
            label_directory="labels",
            image_suffixes=(".tif",),
        ),
        approximate_size="~5 GB",
        quirks=("Source imagery is mixed-provenance, so the per-region licence is not uniform.",),
    ),
    DatasetId.RSVQA_LR: DatasetRecord(
        dataset_id=DatasetId.RSVQA_LR,
        title="RSVQA Low Resolution",
        task="visual question answering",
        sensor="Sentinel-2",
        resolution="10 m",
        scale="~77,000 question-answer pairs",
        unlocked_in="1.7",
        licence=Licence.UNVERIFIED,
        licence_url="https://rsvqa.sylvainlobry.com/",
        licence_verified=False,
        source_url="https://zenodo.org/records/6344334",
        acquisition="download",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_SIDECAR,
            split_directories={
                DatasetSplit.TRAIN: ".",
                DatasetSplit.VALIDATION: ".",
                DatasetSplit.TEST: ".",
            },
            image_directories=("Images_LR",),
            label_file="all_questions.json",
            image_suffixes=(".tif",),
        ),
        approximate_size="~200 MB",
        quirks=(
            "Answers are drawn from a small closed vocabulary, and counting questions are bucketed rather "
            "than exact. A model scored with exact-match against free text will look far worse than it is.",
        ),
    ),
    DatasetId.RSVQA_HR: DatasetRecord(
        dataset_id=DatasetId.RSVQA_HR,
        title="RSVQA High Resolution",
        task="visual question answering",
        sensor="aerial",
        resolution="15 cm",
        scale="~1M question-answer pairs",
        unlocked_in="1.7",
        licence=Licence.UNVERIFIED,
        licence_url="https://rsvqa.sylvainlobry.com/",
        licence_verified=False,
        source_url="https://zenodo.org/records/6344367",
        acquisition="download",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_SIDECAR,
            split_directories={
                DatasetSplit.TRAIN: ".",
                DatasetSplit.VALIDATION: ".",
                DatasetSplit.TEST: ".",
            },
            image_directories=("Data",),
            label_file="all_questions.json",
            image_suffixes=(".tif",),
        ),
        approximate_size="~15 GB",
        quirks=("Two test splits, and the harder one is the one papers report. Using test set 1 by "
                "accident produces a number that cannot be compared with anything published.",),
    ),
    DatasetId.VRSBENCH: DatasetRecord(
        dataset_id=DatasetId.VRSBENCH,
        title="VRSBench",
        task="captioning, grounding and VQA - the primary VLM benchmark",
        sensor="VHR optical",
        resolution="0.5-1 m",
        scale="~29,000 human-verified images",
        unlocked_in="1.7",
        licence=Licence.CC_BY_NC_4_0,
        licence_url="https://huggingface.co/datasets/xiang709/VRSBench",
        licence_verified=False,
        source_url="https://huggingface.co/datasets/xiang709/VRSBench",
        acquisition="download",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_SIDECAR,
            split_directories={DatasetSplit.TRAIN: ".", DatasetSplit.TEST: "."},
            image_directories=("Images_val",),
            label_file="VRSBench_EVAL_vqa.json",
            image_suffixes=(".png", ".jpg"),
        ),
        approximate_size="~3 GB",
        quirks=(
            "The PDF makes this the primary VLM benchmark, so its numbers are the ones that get quoted. "
            "Human-verified, which is why it is trusted, and non-commercial, which is why nothing derived "
            "from it can be sold.",
        ),
    ),
    DatasetId.DIOR_RSVG: DatasetRecord(
        dataset_id=DatasetId.DIOR_RSVG,
        title="DIOR-RSVG",
        task="referring expression grounding (boxes)",
        sensor="VHR optical",
        resolution="0.5-30 m",
        scale="~27,000 referring expressions",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://github.com/ZhanYang-nwpu/RSVG-pytorch",
        licence_verified=False,
        source_url="https://github.com/ZhanYang-nwpu/RSVG-pytorch",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_ANNOTATION,
            split_directories={
                DatasetSplit.TRAIN: ".",
                DatasetSplit.VALIDATION: ".",
                DatasetSplit.TEST: ".",
            },
            image_directories=("JPEGImages",),
            label_directory="Annotations",
            image_suffixes=(".jpg",),
        ),
        approximate_size="~1 GB",
        quirks=("Built on DIOR's imagery, so acquiring both stores the same pictures twice.",),
    ),
    DatasetId.RRSIS_D: DatasetRecord(
        dataset_id=DatasetId.RRSIS_D,
        title="RRSIS-D",
        task="referring expression segmentation (masks)",
        sensor="VHR optical",
        resolution="various",
        scale="~17,000 expression-mask pairs",
        unlocked_in="1.6",
        licence=Licence.UNVERIFIED,
        licence_url="https://github.com/Lsan2401/RMSIN",
        licence_verified=False,
        source_url="https://github.com/Lsan2401/RMSIN",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.IMAGE_MASK,
            split_directories={DatasetSplit.TRAIN: ".", DatasetSplit.TEST: "."},
            image_directories=("JPEGImages",),
            label_directory="ann_split",
            image_suffixes=(".jpg",),
        ),
        approximate_size="~3 GB",
        quirks=("Mask-level grounding, which the PDF marks Advanced - the evidence it produces is a "
                "polygon rather than a box, which is what the evidence chain actually wants.",),
    ),
    DatasetId.SEN12MS: DatasetRecord(
        dataset_id=DatasetId.SEN12MS,
        title="SEN12MS",
        task="optical-SAR pairing and fusion",
        sensor="Sentinel-1 and Sentinel-2",
        resolution="10 m",
        scale="~180,000 co-registered triplets",
        unlocked_in="1.11",
        licence=Licence.CC_BY_4_0,
        licence_url="https://mediatum.ub.tum.de/1474000",
        licence_verified=False,
        source_url="https://mediatum.ub.tum.de/1474000",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.SCENE_DIRECTORIES,
            split_directories={DatasetSplit.ALL: "."},
            image_directories=("s1", "s2"),
            image_suffixes=(".tif",),
        ),
        approximate_size="~430 GB",
        quirks=(
            "Enormous. Phase 1.11 needs co-registered optical-SAR pairs, not all 180,000 of them - the "
            "acquisition plan is a subset, and downloading the whole thing would exhaust the machine.",
            "Already co-registered, which is exactly what makes it useful and also what makes it "
            "unrepresentative: real acquisitions are not, and 1.11's fusion refuses when they are not.",
        ),
    ),
    DatasetId.BIGEARTHNET_MM: DatasetRecord(
        dataset_id=DatasetId.BIGEARTHNET_MM,
        title="BigEarthNet-MM",
        task="multi-label land-cover classification, optical and SAR",
        sensor="Sentinel-1 and Sentinel-2",
        resolution="10-60 m",
        scale="~590,000 patches, CORINE labels",
        unlocked_in="1.11",
        licence=Licence.CC_BY_4_0,
        licence_url="https://bigearth.net/",
        licence_verified=False,
        source_url="https://bigearth.net/",
        acquisition="manual",
        layout=DatasetLayout(
            kind=LayoutKind.SCENE_DIRECTORIES,
            split_directories={DatasetSplit.ALL: "."},
            image_directories=("BigEarthNet-S1", "BigEarthNet-S2"),
            image_suffixes=(".tif",),
        ),
        approximate_size="~120 GB",
        quirks=(
            "Multi-label, not single-label: a patch carries several CORINE classes at once, and treating "
            "it as single-label silently destroys most of the supervision.",
            "A documented subset of patches is fully covered by seasonal snow or cloud and is excluded by "
            "the published splits. Training on the unfiltered set is not comparable to published numbers.",
        ),
    ),
}
