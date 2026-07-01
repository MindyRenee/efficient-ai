"""Efficient AI — Drop-in OpenAI replacement that routes 80%+ of inference to local models.

Five stacked optimizations behind one API:
1. Semantic caching — 30-50% of queries never hit a model at all
2. Intent classification — routes to the cheapest capable model
3. Local-first inference — Ollama/llama.cpp on your existing hardware, $0/token
4. Quantization awareness — picks the right quant level for your VRAM
5. Speculative decoding — 2-3x throughput on supported backends

Usage:
    from efficient import Client

    client = Client()  # auto-detects Ollama, GPU, cloud keys
    response = client.chat(messages=[{"role": "user", "content": "Summarize this article"}])
    # 88% of the time, this never touches a data center
"""

from efficient.client import Client
from efficient.config import Config
from efficient.local_engine import LocalEngine
from efficient.telemetry import Telemetry

__version__ = "0.1.0"
__all__ = [
    "Client",
    "Config",
    "LocalEngine",
    "Telemetry",
    "create_app",
    "patch_openai",
    "run_server",
]


def patch_openai(client=None):
    """Monkey-patch the OpenAI SDK to route through Efficient AI."""
    from efficient.openai_shim import patch_openai as _patch

    return _patch(client)


def create_app(*args, **kwargs):
    """Create the x402-enabled proxy server app."""
    from efficient.proxy import create_app as _create

    return _create(*args, **kwargs)


def run_server(*args, **kwargs):
    """Run the x402 proxy server."""
    from efficient.proxy import run_server as _run

    return _run(*args, **kwargs)
