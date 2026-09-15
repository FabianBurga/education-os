from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADVISORY = ROOT / "app/modules/copilot/advisory.py"
PROVIDERS = ROOT / "app/modules/copilot/providers.py"


def test_advisory_orchestrator_starts_with_governed_preflight():
    source = ADVISORY.read_text(encoding="utf-8")
    function_start = source.index("def generate_advisory_answer(")
    preflight = source.index(
        "run = begin_copilot_preflight(",
        function_start,
    )
    gateway_call = source.index(
        "provider_result = active_gateway.invoke(",
        preflight,
    )
    assert preflight < gateway_call


def test_provider_adapter_has_fixed_openai_endpoint():
    source = PROVIDERS.read_text(encoding="utf-8")
    assert (
        'endpoint = "https://api.openai.com/v1/responses"'
        in source
    )
    assert "base_url" not in source


def test_provider_secret_is_not_persisted_or_logged():
    provider_source = PROVIDERS.read_text(encoding="utf-8")
    advisory_source = ADVISORY.read_text(encoding="utf-8")

    assert 'os.getenv(self.api_key_env)' in provider_source
    assert "metadata_json" not in provider_source
    assert "api_key" not in advisory_source.lower()
