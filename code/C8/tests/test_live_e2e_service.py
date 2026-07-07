import subprocess
from pathlib import Path

from e2e.service import LiveServiceProcess


def test_service_process_does_not_pipe_stdout(monkeypatch, tmp_path: Path):
    captured = {}

    class FakePopen:
        def __init__(self, command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs

        def poll(self):
            return 0

    monkeypatch.setattr("e2e.service.is_port_open", lambda host, port: False)
    monkeypatch.setattr("e2e.service.subprocess.Popen", FakePopen)

    service = LiveServiceProcess(
        project_dir=tmp_path,
        host="127.0.0.1",
        port=5062,
        model="qwen-plus-2025-07-28",
        reuse_server=False,
    )
    service.start()

    assert captured["kwargs"]["stdout"] == subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] == subprocess.STDOUT
