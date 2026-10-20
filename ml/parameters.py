"""JUCE NormalisableRange mapping, driven exclusively by the C++ export."""
import math
import numbers


def checked_spec(spec, parameter):
    item = spec["parameters"][parameter]
    if item["symmetric_skew"] or item["interval"] != 0:
        raise ValueError("This experiment supports continuous, nonsymmetric JUCE ranges only")
    if not item["minimum"] < item["maximum"] or item["skew"] <= 0:
        raise ValueError("Invalid exported range")
    return item


def normalize(value, parameter, spec):
    item = checked_spec(spec, parameter)
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value) or not item["minimum"] <= value <= item["maximum"]:
        raise ValueError(f"Invalid physical value for {parameter}")
    return ((value - item["minimum"]) / (item["maximum"] - item["minimum"])) ** item["skew"]


def denormalize(value, parameter, spec):
    item = checked_spec(spec, parameter)
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"Invalid normalized value for {parameter}")
    return item["minimum"] + (item["maximum"] - item["minimum"]) * value ** (1 / item["skew"])
