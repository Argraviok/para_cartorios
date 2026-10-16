import pytest

from app.core.config import Settings


def make(**env) -> Settings:
    return Settings(_env_file=None, **env)


def test_new_variable_names_are_accepted(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb+srv://u:p@cluster0.example.net/")
    monkeypatch.setenv("MONGO_DB", "cartorio_db")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:4210, http://exemplo.com")
    s = Settings(_env_file=None)
    assert s.mongodb_uri.startswith("mongodb+srv://") and s.mongodb_db == "cartorio_db"
    assert s.cors_origins == ["http://localhost:4210", "http://exemplo.com"]


def test_legacy_names_and_json_cors_still_work(monkeypatch):
    monkeypatch.setenv("MONGODB_DB", "antigo")
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:4200"]')
    s = Settings(_env_file=None)
    assert s.mongodb_db == "antigo" and s.cors_origins == ["http://localhost:4200"]


def test_provider_follows_the_only_key_present():
    s = make(gemini_api_key="g", gemini_model="gemini-x")
    assert (s.llm_provider, s.llm_model) == ("gemini", "gemini-x")
    assert (s.embedding_provider, s.embedding_model) == ("gemini", "gemini-embedding-001")

    s = make(openai_api_key="o", gemini_api_key="  ")
    assert (s.llm_provider, s.llm_model) == ("openai", "gpt-4o-mini")
    assert s.embedding_model == "text-embedding-3-small"


def test_both_keys_require_explicit_provider():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        make(gemini_api_key="g", openai_api_key="o")
    s = make(gemini_api_key="g", openai_api_key="o", llm_provider="openai")
    assert s.llm_model == "gpt-4o-mini" and s.embedding_provider == "openai"


def test_no_keys_disables_llm_and_offline_still_embeds_with_available_key():
    s = make()
    assert s.llm_provider is None and s.embedding_provider is None
    s = make(llm_provider="offline", gemini_api_key="g")
    assert s.llm_model is None and s.embedding_provider == "gemini"


def test_fallback_models_parse_from_comma_list(monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite, gemini-flash-lite-latest")
    assert Settings(_env_file=None).gemini_fallback_models == ["gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
