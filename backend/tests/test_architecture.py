import scripts.check_architecture as architecture


def test_architecture_boundaries() -> None:
    assert architecture.main() == 0


def test_application_services_do_not_depend_on_fastapi_http_types() -> None:
    violations = architecture.scan_service_fastapi_dependencies()
    assert violations == []


def test_architecture_main_enforces_service_fastapi_scan(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        architecture,
        "scan_service_fastapi_dependencies",
        lambda: [
            "app/services/bad_service.py:1: fastapi: "
            "services cannot depend on FastAPI HTTP types"
        ],
    )

    assert architecture.main() == 1
    output = capsys.readouterr().out
    assert "services cannot depend on FastAPI HTTP types" in output
