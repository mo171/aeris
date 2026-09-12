"""The fixed decisions of change detection: where a probability becomes a change, and how far a radar return must move to count.

what  : `CHANGE_PROBABILITY_THRESHOLD`, `SAR_LOG_RATIO_THRESHOLD_DECIBELS`, `CHANGE_CLASS_INDEX`.
where : Read by `services/change_detection/`. Thresholds are scientific policy, not machine settings.
how   : 0.5 on a two-class softmax is the decision the network was trained to make - the argmax - and
        moving it trades recall for precision without telling the operator. It is a constant so a later
        calibration is one edit with a citation, not a drift.

        3 dB is a doubling of backscatter power. Below it, the difference between two Sentinel-1 dates is
        speckle and incidence-angle variation more often than the ground; above it, the surface changed
        its roughness or dielectric state. Standard in the flood and deforestation literature, and a
        fixed number so two dates are compared on one scale (the same argument as the fixed dB display
        domain in 1.3).
"""

from typing import Final

CHANGE_PROBABILITY_THRESHOLD: Final[float] = 0.5
SAR_LOG_RATIO_THRESHOLD_DECIBELS: Final[float] = 3.0

# The softmax channel that means "changed" in a two-class change model. 0 is "unchanged".
CHANGE_CLASS_INDEX: Final[int] = 1
