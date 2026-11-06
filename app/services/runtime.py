"""Lightweight inference-library presence check; no model imports or network."""

from importlib.util import find_spec

INFERENCE_MODULES = ("torch", "transformers", "huggingface_hub", "lab")


def inference_dependencies():
    return {name: find_spec(name) is not None for name in INFERENCE_MODULES}
