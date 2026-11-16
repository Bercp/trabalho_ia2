import os

import penal.config as config


def test_reads_updated_api_configuration_without_server_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=first-model\n", encoding="utf-8")
    os.utime(env_file, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    assert config.settings().llm_model == "first-model"
    env_file.write_text("LLM_MODEL=second-model\n", encoding="utf-8")
    os.utime(env_file, ns=(1_700_000_001_000_000_000, 1_700_000_001_000_000_000))
    assert config.settings().llm_model == "second-model"
    config._read_settings.cache_clear()
