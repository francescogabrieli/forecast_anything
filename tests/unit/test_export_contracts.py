import json
import subprocess
import sys


def test_openapi_422_descriptions_are_stable_across_python_versions(tmp_path):
    subprocess.run(
        [sys.executable, "scripts/export_contracts.py", str(tmp_path)], check=True
    )
    openapi = json.loads((tmp_path / "openapi.json").read_text(encoding="utf-8"))
    descriptions = {
        operation["responses"]["422"]["description"]
        for path in openapi["paths"].values()
        for operation in path.values()
        if "422" in operation.get("responses", {})
    }

    assert descriptions == {"Unprocessable Content"}
