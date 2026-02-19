"""
Unit tests for core instance utilities.
"""
import builtins
import io

from app.core.instance import detect_platform


def test_detect_platform_podman_marker(monkeypatch):
    """Detect container when Podman marker exists."""
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda p: p == "/run/.containerenv")
    monkeypatch.setattr("app.core.instance.os.getenv", lambda _: None)

    assert detect_platform() == "container"


def test_detect_platform_docker_marker(monkeypatch):
    """Detect container when Docker marker exists."""
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda p: p == "/.dockerenv")
    monkeypatch.setattr("app.core.instance.os.getenv", lambda _: None)

    assert detect_platform() == "container"


def test_detect_platform_docker_cgroup(monkeypatch):
    """Detect container when cgroup contains docker pattern."""
    def fake_open(path, mode="r", *args, **kwargs):
        if path == "/proc/1/cgroup":
            return io.StringIO("12:devices:/docker/abc123")
        raise FileNotFoundError

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda _: False)
    monkeypatch.setattr("app.core.instance.os.getenv", lambda _: None)

    assert detect_platform() == "container"


def test_detect_platform_kubernetes_cgroup(monkeypatch):
    """Detect container when cgroup contains kubepods pattern."""
    def fake_open(path, mode="r", *args, **kwargs):
        if path == "/proc/1/cgroup":
            return io.StringIO("12:devices:/kubepods/besteffort/pod123")
        raise FileNotFoundError

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda _: False)
    monkeypatch.setattr("app.core.instance.os.getenv", lambda _: None)

    assert detect_platform() == "container"


def test_detect_platform_lxc_cgroup(monkeypatch):
    """Detect container when cgroup contains lxc pattern."""
    def fake_open(path, mode="r", *args, **kwargs):
        if path == "/proc/1/cgroup":
            return io.StringIO("12:devices:/lxc/container123")
        raise FileNotFoundError

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda _: False)
    monkeypatch.setattr("app.core.instance.os.getenv", lambda _: None)

    assert detect_platform() == "container"


def test_detect_platform_containerd_cgroup(monkeypatch):
    """Detect container when cgroup contains containerd pattern."""
    def fake_open(path, mode="r", *args, **kwargs):
        if path == "/proc/1/cgroup":
            return io.StringIO("12:devices:/system.slice/containerd.service")
        raise FileNotFoundError

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda _: False)
    monkeypatch.setattr("app.core.instance.os.getenv", lambda _: None)

    assert detect_platform() == "container"


def test_detect_platform_container_env_var(monkeypatch):
    """Detect container when container environment variable is set."""
    monkeypatch.setattr(builtins, "open", lambda *_, **__: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda _: False)
    monkeypatch.setattr("app.core.instance.os.getenv", lambda k: "podman" if k == "container" else None)

    assert detect_platform() == "container"


def test_detect_platform_bare_metal(monkeypatch):
    """Detect bare-metal when no container markers found."""
    monkeypatch.setattr(builtins, "open", lambda *_, **__: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda _: False)
    monkeypatch.setattr("app.core.instance.os.getenv", lambda _: None)

    assert detect_platform() == "bare-metal"


def test_detect_platform_cgroup_permission_error(monkeypatch):
    """Handle permission errors gracefully and check other markers."""
    def fake_open(path, mode="r", *args, **kwargs):
        if path == "/proc/1/cgroup":
            raise PermissionError("Access denied")
        raise FileNotFoundError

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr("app.core.instance.os.path.exists", lambda _: False)
    monkeypatch.setattr("app.core.instance.os.getenv", lambda _: None)

    assert detect_platform() == "bare-metal"
