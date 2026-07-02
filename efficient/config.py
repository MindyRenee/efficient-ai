"""Auto-detection of local compute resources, cloud API keys, and Ollama instances.

Discovers:
- Ollama installation and running models
- Available GPU VRAM (NVIDIA, Apple Silicon, AMD)
- Cloud API keys from environment variables
- Optimal model recommendations based on hardware
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# ─── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class GPUInfo:
    """Detected GPU information."""

    vendor: str = "unknown"  # nvidia, apple, amd, none
    name: str = "unknown"
    vram_mb: int = 0  # VRAM in MB (unified memory for Apple)
    compute_capability: str = ""
    device_count: int = 0

    @property
    def available(self) -> bool:
        return self.vendor != "none" and self.vram_mb > 0


@dataclass
class OllamaInfo:
    """Detected Ollama installation info."""

    installed: bool = False
    running: bool = False
    host: str = "http://localhost:11434"
    models: list[str] = field(default_factory=list)
    version: str = ""


@dataclass
class CloudKeys:
    """Detected cloud API keys."""

    openai: str | None = None
    openrouter: str | None = None
    groq: str | None = None
    together: str | None = None

    @property
    def any_available(self) -> bool:
        return any([self.openai, self.openrouter, self.groq, self.together])

    def available_providers(self) -> list[str]:
        providers = []
        if self.openai:
            providers.append("openai")
        if self.openrouter:
            providers.append("openrouter")
        if self.groq:
            providers.append("groq")
        if self.together:
            providers.append("together")
        return providers


@dataclass
class Config:
    """Full configuration for Efficient AI.

    Auto-detects on first instantiation, then persists to ~/.efficient/config.json.
    Users can override any field manually.
    """

    # Local
    ollama: OllamaInfo = field(default_factory=OllamaInfo)
    gpu: GPUInfo = field(default_factory=GPUInfo)

    # Cloud
    cloud: CloudKeys = field(default_factory=CloudKeys)

    # Routing preferences
    local_first: bool = True  # Try local before cloud
    cache_enabled: bool = True  # Semantic caching
    cache_similarity_threshold: float = 0.92
    cache_db_path: str = ""

    # Model preferences (auto-set based on hardware)
    preferred_local_model: str = ""
    preferred_cloud_model: str = "gpt-4o-mini"
    fallback_cloud_model: str = "gpt-4o"

    # Telemetry
    track_costs: bool = True
    telemetry_db_path: str = ""

    # Behavior
    auto_pull_models: bool = False  # Auto `ollama pull` if model missing
    max_retries: int = 2
    timeout_seconds: float = 120.0

    # Internal
    _config_path: str = ""

    # ─── Persistence ──────────────────────────────────────────────────────

    def save(self) -> None:
        """Persist config to ~/.efficient/config.json."""
        path = Path(self._config_path) if self._config_path else self._default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._to_dict()
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls) -> Config:
        """Load config from disk, or auto-detect if not present."""
        path = cls._default_config_path()
        if path.exists():
            data = json.loads(path.read_text())
            config = cls._from_dict(data)
            config._config_path = str(path)
            return config
        # Auto-detect on first run
        config = cls.autodetect()
        config._config_path = str(path)
        config._init_paths()
        config.save()
        return config

    def _init_paths(self) -> None:
        home = Path.home() / ".efficient"
        home.mkdir(parents=True, exist_ok=True)
        if not self.cache_db_path:
            self.cache_db_path = str(home / "cache.db")
        if not self.telemetry_db_path:
            self.telemetry_db_path = str(home / "telemetry.db")

    @staticmethod
    def _default_config_path() -> Path:
        return Path.home() / ".efficient" / "config.json"

    def _to_dict(self) -> dict:
        return {
            "ollama": {
                "installed": self.ollama.installed,
                "running": self.ollama.running,
                "host": self.ollama.host,
                "models": self.ollama.models,
                "version": self.ollama.version,
            },
            "gpu": {
                "vendor": self.gpu.vendor,
                "name": self.gpu.name,
                "vram_mb": self.gpu.vram_mb,
                "compute_capability": self.gpu.compute_capability,
                "device_count": self.gpu.device_count,
            },
            "cloud": {
                "openai": self.cloud.openai,
                "openrouter": self.cloud.openrouter,
                "groq": self.cloud.groq,
                "together": self.cloud.together,
            },
            "local_first": self.local_first,
            "cache_enabled": self.cache_enabled,
            "cache_similarity_threshold": self.cache_similarity_threshold,
            "cache_db_path": self.cache_db_path,
            "preferred_local_model": self.preferred_local_model,
            "preferred_cloud_model": self.preferred_cloud_model,
            "fallback_cloud_model": self.fallback_cloud_model,
            "track_costs": self.track_costs,
            "telemetry_db_path": self.telemetry_db_path,
            "auto_pull_models": self.auto_pull_models,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def _from_dict(cls, data: dict) -> Config:
        return cls(
            ollama=OllamaInfo(
                installed=data.get("ollama", {}).get("installed", False),
                running=data.get("ollama", {}).get("running", False),
                host=data.get("ollama", {}).get("host", "http://localhost:11434"),
                models=data.get("ollama", {}).get("models", []),
                version=data.get("ollama", {}).get("version", ""),
            ),
            gpu=GPUInfo(
                vendor=data.get("gpu", {}).get("vendor", "unknown"),
                name=data.get("gpu", {}).get("name", "unknown"),
                vram_mb=data.get("gpu", {}).get("vram_mb", 0),
                compute_capability=data.get("gpu", {}).get("compute_capability", ""),
                device_count=data.get("gpu", {}).get("device_count", 0),
            ),
            cloud=CloudKeys(
                openai=data.get("cloud", {}).get("openai"),
                openrouter=data.get("cloud", {}).get("openrouter"),
                groq=data.get("cloud", {}).get("groq"),
                together=data.get("cloud", {}).get("together"),
            ),
            local_first=data.get("local_first", True),
            cache_enabled=data.get("cache_enabled", True),
            cache_similarity_threshold=data.get("cache_similarity_threshold", 0.92),
            cache_db_path=data.get("cache_db_path", ""),
            preferred_local_model=data.get("preferred_local_model", ""),
            preferred_cloud_model=data.get("preferred_cloud_model", "gpt-4o-mini"),
            fallback_cloud_model=data.get("fallback_cloud_model", "gpt-4o"),
            track_costs=data.get("track_costs", True),
            telemetry_db_path=data.get("telemetry_db_path", ""),
            auto_pull_models=data.get("auto_pull_models", False),
            max_retries=data.get("max_retries", 2),
            timeout_seconds=data.get("timeout_seconds", 120.0),
        )

    # ─── Auto-Detection ────────────────────────────────────────────────────

    @classmethod
    def autodetect(cls) -> Config:
        """Run full auto-detection of hardware, Ollama, and cloud keys."""
        config = cls()
        config.gpu = _detect_gpu()
        config.ollama = _detect_ollama()
        config.cloud = _detect_cloud_keys()
        config._init_paths()

        # Auto-select best local model based on VRAM
        config.preferred_local_model = _recommend_local_model(config.gpu, config.ollama)

        return config

    def refresh(self) -> None:
        """Re-run detection and update config."""
        self.gpu = _detect_gpu()
        self.ollama = _detect_ollama()
        self.cloud = _detect_cloud_keys()
        self.preferred_local_model = _recommend_local_model(self.gpu, self.ollama)
        self.save()

    def summary(self) -> str:
        """Human-readable config summary."""
        lines = [
            "Efficient AI Configuration",
            "=" * 50,
            "",
            f"GPU: {self.gpu.name} ({self.gpu.vendor})",
            f"  VRAM: {self.gpu.vram_mb / 1024:.1f} GB"
            if self.gpu.vram_mb
            else "  VRAM: not detected",
            f"  Available: {'yes' if self.gpu.available else 'no'}",
            "",
            f"Ollama: {'installed' if self.ollama.installed else 'not installed'}",
            f"  Running: {'yes' if self.ollama.running else 'no'}",
            f"  Host: {self.ollama.host}",
            f"  Models: {', '.join(self.ollama.models) if self.ollama.models else 'none'}",
            "",
            f"Cloud providers: {', '.join(self.cloud.available_providers()) if self.cloud.any_available else 'none'}",
            "",
            f"Preferred local model: {self.preferred_local_model or 'none'}",
            f"Preferred cloud model: {self.preferred_cloud_model}",
            f"Fallback cloud model: {self.fallback_cloud_model}",
            "",
            f"Local-first: {self.local_first}",
            f"Cache enabled: {self.cache_enabled} (threshold: {self.cache_similarity_threshold})",
            f"Auto-pull models: {self.auto_pull_models}",
        ]
        return "\n".join(lines)


# ─── Detection Functions ───────────────────────────────────────────────────────


def _detect_gpu() -> GPUInfo:
    """Detect available GPU hardware."""
    info = GPUInfo()

    # Try NVIDIA via nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name,memory.total,compute_cap",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                first = lines[0].split(", ")
                if len(first) >= 3:
                    info.vendor = "nvidia"
                    info.name = first[0].strip()
                    info.vram_mb = int(float(first[1].strip()))
                    info.compute_capability = first[2].strip()
                    info.device_count = len(lines)
                    return info
        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
            pass

    # Try Apple Silicon
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                displays = data.get("SPDisplaysDataType", [])
                for gpu_data in displays:
                    vendor = gpu_data.get("spdisplays_vendor", "")
                    if (
                        "apple" in vendor.lower()
                        or "apple" in gpu_data.get("spdisplays_device_name", "").lower()
                    ):
                        info.vendor = "apple"
                        info.name = gpu_data.get("spdisplays_device_name", "Apple Silicon")
                        # Apple unified memory — read total system RAM as proxy
                        mem_result = subprocess.run(
                            ["sysctl", "-n", "hw.memsize"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if mem_result.returncode == 0:
                            total_bytes = int(mem_result.stdout.strip())
                            info.vram_mb = total_bytes // (1024 * 1024)
                        info.device_count = 1
                        return info
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

    # Try AMD via rocm-smi
    rocm_smi = shutil.which("rocm-smi")
    if rocm_smi:
        try:
            result = subprocess.run(
                [rocm_smi, "--showmeminfo", "vram", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                for card_id, card_data in data.items():
                    if isinstance(card_data, dict):
                        vram = card_data.get("VRAM Total Memory (B)", 0)
                        if vram:
                            info.vendor = "amd"
                            info.name = f"AMD GPU ({card_id})"
                            info.vram_mb = int(vram) // (1024 * 1024)
                            info.device_count = len(data)
                            return info
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

    # No GPU detected
    info.vendor = "none"
    return info


def _detect_ollama(host: str = "http://localhost:11434") -> OllamaInfo:
    """Detect Ollama installation and running models."""
    info = OllamaInfo(host=host)

    # Check if ollama binary exists
    ollama_bin = shutil.which("ollama")
    info.installed = ollama_bin is not None

    if not info.installed:
        return info

    # Check if Ollama server is running and get models
    try:
        with httpx.Client(timeout=5.0) as client:
            # Get version
            resp = client.get(f"{host}/api/version")
            if resp.status_code == 200:
                info.running = True
                info.version = resp.json().get("version", "")

            # Get installed models
            resp = client.get(f"{host}/api/tags")
            if resp.status_code == 200:
                models_data = resp.json().get("models", [])
                info.models = [m["name"] for m in models_data]
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        info.running = False

    return info


def _detect_cloud_keys() -> CloudKeys:
    """Detect cloud API keys from environment variables."""
    return CloudKeys(
        openai=os.environ.get("OPENAI_API_KEY"),
        openrouter=os.environ.get("OPENROUTER_API_KEY"),
        groq=os.environ.get("GROQ_API_KEY"),
        together=os.environ.get("TOGETHER_API_KEY"),
    )


def _recommend_local_model(gpu: GPUInfo, ollama: OllamaInfo) -> str:
    """Recommend the best local model based on available VRAM.
    Targets the Q4_K_M quantization sweet spot (25-30% of full VRAM, ~1.4 MMLU point loss).
    """
    vram_gb = gpu.vram_mb / 1024

    # If Ollama has models already, prefer the largest capable one
    if ollama.models:
        # Prefer models we know are good
        priority = [
            "qwen2.5:72b",
            "qwen2.5:32b",
            "qwen2.5:14b",
            "qwen2.5:7b",
            "llama3.3:70b",
            "llama3.1:8b",
            "deepseek-v4:flash",
            "deepseek-r1:14b",
            "deepseek-r1:7b",
            "mistral:7b",
            "gemma2:9b",
            "phi3:mini",
        ]
        for model in priority:
            for installed in ollama.models:
                if model in installed or installed.startswith(model.split(":")[0]):
                    return installed
        # Fall back to first available
        return ollama.models[0]

    # Recommend based on VRAM at Q4_K_M
    if vram_gb >= 48:
        return "qwen2.5:32b"  # 32B at Q4 ≈ 20GB, fits comfortably
    if vram_gb >= 24:
        return "qwen2.5:14b"  # 14B at Q4 ≈ 9GB
    if vram_gb >= 12:
        return "qwen2.5:7b"  # 7B at Q4 ≈ 4.5GB
    if vram_gb >= 8:
        return "llama3.1:8b"  # 8B at Q4 ≈ 5GB
    if vram_gb >= 4:
        return "phi3:mini"  # 3.8B at Q4 ≈ 2.3GB
    return "qwen2.5:7b"  # Will run on CPU, slowly
