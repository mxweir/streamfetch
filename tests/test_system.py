import json
import zipfile
from io import BytesIO
from types import SimpleNamespace

from streamfetch.system import (
    HealthStatus,
    dependency_guidance,
    diagnostics_archive,
    run_health_checks,
)


def test_dependency_guidance_is_platform_specific():
    assert "brew install ffmpeg" in dependency_guidance("Darwin")["ffmpeg"]
    assert "winget install" in dependency_guidance("Windows")["ffmpeg"]
    assert "apt install ffmpeg" in dependency_guidance("Linux")["ffmpeg"]


def test_health_checks_report_tools_and_storage(monkeypatch, tmp_path):
    def command_version(command, *_arguments):
        return {"ffmpeg": "ffmpeg 8", "node": "v24"}.get(command)

    monkeypatch.setattr("streamfetch.system._command_version", command_version)
    checks = run_health_checks(tmp_path)
    by_key = {check.key: check for check in checks}

    assert by_key["ffmpeg"].status is HealthStatus.READY
    assert by_key["javascript"].status is HealthStatus.READY
    assert by_key["storage"].status is HealthStatus.READY
    assert by_key["storage"].required is True


def test_diagnostics_exclude_sensitive_job_data(monkeypatch, tmp_path):
    monkeypatch.setattr("streamfetch.system._command_version", lambda *_args: None)
    checks = run_health_checks(tmp_path)
    job = SimpleNamespace(
        status="failed",
        url="https://example.invalid/private",
        filename="secret-track.mp3",
    )

    bundle = diagnostics_archive(checks, language="Deutsch", jobs=(job,))

    with zipfile.ZipFile(BytesIO(bundle)) as archive:
        payload = json.loads(archive.read("streamfetch-diagnostics.json"))
    rendered = json.dumps(payload)
    assert payload["language"] == "Deutsch"
    assert payload["job_counts"] == {"failed": 1}
    assert "example.invalid" not in rendered
    assert "secret-track" not in rendered
