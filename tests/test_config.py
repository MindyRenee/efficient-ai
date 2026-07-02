"""
Tests for the config module — auto-detection and persistence.
"""

from pathlib import Path

from efficient.config import CloudKeys, Config, GPUInfo, OllamaInfo


class TestConfig:
    def test_autodetect_returns_config(self):
        """Autodetect should return a valid Config object."""
        config = Config.autodetect()
        assert isinstance(config, Config)
        assert isinstance(config.gpu, GPUInfo)
        assert isinstance(config.ollama, OllamaInfo)
        assert isinstance(config.cloud, CloudKeys)

    def test_save_and_load(self, tmp_path, monkeypatch):
        """Config should persist and reload correctly."""
        # Mock home directory
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Save
        config = Config.autodetect()
        config._init_paths()
        config.preferred_local_model = "test-model"
        config.save()

        # Verify file exists
        config_file = tmp_path / ".efficient" / "config.json"
        assert config_file.exists()

        # Load
        loaded = Config.load()
        assert loaded.preferred_local_model == "test-model"

    def test_cloud_keys_detection(self, monkeypatch):
        """Cloud keys should be detected from environment."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")
        monkeypatch.setenv("GROQ_API_KEY", "test-key-456")
        keys = CloudKeys(
            openai="test-key-123",
            groq="test-key-456",
        )
        assert keys.openai == "test-key-123"
        assert keys.groq == "test-key-456"
        assert "openai" in keys.available_providers()
        assert "groq" in keys.available_providers()

    def test_cloud_keys_none(self):
        keys = CloudKeys()
        assert not keys.any_available
        assert keys.available_providers() == []

    def test_gpu_info_properties(self):
        gpu = GPUInfo(vendor="nvidia", name="RTX 4090", vram_mb=24576)
        assert gpu.available
        assert gpu.vendor == "nvidia"

        gpu_none = GPUInfo(vendor="none")
        assert not gpu_none.available

    def test_summary_output(self):
        config = Config(
            gpu=GPUInfo(vendor="nvidia", name="RTX 4090", vram_mb=24576),
            ollama=OllamaInfo(installed=True, running=True, models=["qwen2.5:7b"]),
            cloud=CloudKeys(openai="test-key"),
            preferred_local_model="qwen2.5:7b",
        )
        summary = config.summary()
        assert "RTX 4090" in summary
        assert "qwen2.5:7b" in summary
        assert "openai" in summary

    def test_refresh_updates_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = Config()
        config._init_paths()
        config.refresh()
        assert isinstance(config.gpu, GPUInfo)
