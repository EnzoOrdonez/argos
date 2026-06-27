import json

from soar.response.forensics.velociraptor_collector import (
    DEFAULT_RANSOMWARE_TRIAGE_ARTIFACTS,
    build_collect_client_query,
    collect_with_velociraptor,
)


def test_build_collect_client_query_contains_expected_parts():
    query = build_collect_client_query(
        client_id="C.1234567890abcdef",
        artifacts=DEFAULT_RANSOMWARE_TRIAGE_ARTIFACTS,
    )

    assert "collect_client" in query
    assert "C.1234567890abcdef" in query
    assert "Generic.Client.Info" in query
    assert "Windows.System.Pslist" in query
    assert "Windows.Network.Netstat" in query


def test_collect_with_velociraptor_dry_run_creates_metadata(tmp_path):
    host_map_path = tmp_path / "velociraptor_hosts.json"
    host_map_path.write_text(
        json.dumps({"WIN-VICTIM-01": "C.1234567890abcdef"}),
        encoding="utf-8",
    )

    result = collect_with_velociraptor(
        incident_id="INC-TEST-VR-001",
        host_id="WIN-VICTIM-01",
        host_map_path=host_map_path,
        api_config_path=tmp_path / "api.config.yaml",
        velociraptor_binary="velociraptor",
        output_root=tmp_path / "evidence",
        dry_run=True,
    )

    output_dir = tmp_path / "evidence" / "INC-TEST-VR-001" / "velociraptor"

    assert result.status == "dry_run"
    assert result.host_id == "WIN-VICTIM-01"
    assert result.client_id == "C.1234567890abcdef"
    assert output_dir.exists()

    assert (output_dir / "velociraptor_request.json").exists()
    assert (output_dir / "velociraptor_command_result.json").exists()
    assert (output_dir / "velociraptor_collection_result.json").exists()
    assert (output_dir / "manifest.json").exists()


def test_collect_with_custom_artifacts(tmp_path):
    host_map_path = tmp_path / "velociraptor_hosts.json"
    host_map_path.write_text(
        json.dumps({"WIN-VICTIM-01": "C.1234567890abcdef"}),
        encoding="utf-8",
    )

    result = collect_with_velociraptor(
        incident_id="INC-TEST-VR-002",
        host_id="WIN-VICTIM-01",
        host_map_path=host_map_path,
        api_config_path=tmp_path / "api.config.yaml",
        output_root=tmp_path / "evidence",
        artifacts=["Generic.Client.Info"],
        dry_run=True,
    )

    assert result.status == "dry_run"
    assert result.artifacts == ["Generic.Client.Info"]