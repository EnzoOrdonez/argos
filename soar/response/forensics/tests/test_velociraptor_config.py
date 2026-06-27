import json

import pytest

from soar.response.forensics.velociraptor_config import (
    VelociraptorIntegrationConfig,
    load_host_map,
    resolve_client_id,
)


def test_load_host_map_returns_mapping(tmp_path):
    host_map_path = tmp_path / "velociraptor_hosts.json"
    host_map_path.write_text(
        json.dumps({"WIN-VICTIM-01": "C.1234567890abcdef"}),
        encoding="utf-8",
    )

    host_map = load_host_map(host_map_path)

    assert host_map == {"WIN-VICTIM-01": "C.1234567890abcdef"}


def test_resolve_client_id_returns_expected_client_id():
    host_map = {"WIN-VICTIM-01": "C.1234567890abcdef"}

    client_id = resolve_client_id("WIN-VICTIM-01", host_map)

    assert client_id == "C.1234567890abcdef"


def test_resolve_client_id_raises_error_when_host_is_missing():
    host_map = {"WIN-VICTIM-01": "C.1234567890abcdef"}

    with pytest.raises(ValueError, match="No Velociraptor client_id mapped"):
        resolve_client_id("UNKNOWN-HOST", host_map)


def test_default_config_paths_are_defined():
    config = VelociraptorIntegrationConfig()

    assert config.api_config_path == "config/api.config.yaml"
    assert config.host_map_path == "config/velociraptor_hosts.json"
    assert config.output_root == "evidence"