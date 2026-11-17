"""The live self-test logic, run against the fake cloud."""
import asyncio

from server.selftest import diagnose_azure_translator, run_all


def test_selftest_all_green(cloud_settings):
    r = asyncio.run(run_all(cloud_settings()))
    s = r["summary"]
    assert s["both_directions_translate"]
    assert set(s["translation_working"]) == {"azure", "google_free", "mymemory"}
    assert s["azure_tts_te"] and s["azure_tts_en"] and s["azure_stt_te"] and s["azure_stt_en"]
    assert "google" in s["server_voice_by_language"]["ta"] and "google" in s["server_voice_by_language"]["hi"]
    assert s["server_voice_by_language"]["te"][0] == "azure"
    assert any(r["check"] == "translate en->ta" and r["ok"] for r in r["translation"])
    assert "azure_translator_diagnosis" not in r
    assert "good-key" not in str(r) and "speech-key" not in str(r)


def test_selftest_diagnoses_wrong_region(cloud_settings):
    r = asyncio.run(run_all(cloud_settings(azure_translator_region="westus")))
    diag = r["azure_translator_diagnosis"]
    winners = [d for d in diag if d["ok"]]
    assert winners and winners[0]["region_header"] == "centralindia"
    assert r["summary"]["both_directions_translate"]  # free fallbacks still work


def test_diagnosis_flags_speech_key_reuse(cloud_settings):
    s = cloud_settings(azure_translator_key="same", azure_speech_key="same")
    diag = asyncio.run(diagnose_azure_translator(s))
    assert any(d["variant"] == "note" and "identical" in d["error"] for d in diag)


def test_selftest_without_keys_skips_azure():
    from server.config import Settings
    s = Settings(google_free_endpoint="http://127.0.0.1:9/x", mymemory_endpoint="http://127.0.0.1:9/y",
                 provider_timeout_s=1)
    r = asyncio.run(run_all(s))
    assert r["speech"][0]["ok"] is False and "skipped" in r["speech"][0]["error"]
    assert r["summary"]["both_directions_translate"] is False
