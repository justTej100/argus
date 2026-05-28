# Lowercase alias — main.py imports `from agents.pipeline import ResearchPipeline`
# Python module names are case-sensitive on Linux.
from agents.Pipeline import ResearchPipeline, PipelineResult

__all__ = ["ResearchPipeline", "PipelineResult"]
