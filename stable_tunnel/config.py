from __future__ import annotations

import getpass
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

SERVICE_NAME = "ssh-reverse-tunnel"
CLEAN_SCRIPT_NAME = "stable-tunnel-clean-remote-port.sh"
DEFAULT_INSTALL_DIR = "/usr/local/bin"
SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")
CONFIG_DIR = Path.home() / ".config" / "stable-tunnel"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.toml"


@dataclass
class TunnelConfig:
    remote_host: str
    remote_port: int
    local_host: str = "127.0.0.1"
    local_port: int = 22
    user: str = ""
    connect_timeout: int = 3
    server_alive_interval: int = 3
    server_alive_count_max: int = 2
    strict_host_key_checking: bool = False
    restart_sec: int = 5
    clean_remote_before_start: bool = True
    install_dir: str = DEFAULT_INSTALL_DIR
    ssh_verbose: bool = False

    def __post_init__(self) -> None:
        if not self.user:
            self.user = getpass.getuser()

    @property
    def service_unit_name(self) -> str:
        return f"{SERVICE_NAME}.service"

    @property
    def service_unit_path(self) -> Path:
        return SYSTEMD_UNIT_DIR / self.service_unit_name

    @property
    def clean_script_path(self) -> Path:
        return Path(self.install_dir) / CLEAN_SCRIPT_NAME

    def validate(self) -> None:
        if not self.remote_host.strip():
            raise ValueError("remote_host 不能为空")
        if not 1 <= self.remote_port <= 65535:
            raise ValueError("remote_port 必须在 1-65535 之间")
        if not 1 <= self.local_port <= 65535:
            raise ValueError("local_port 必须在 1-65535 之间")
        if not self.user.strip():
            raise ValueError("user 不能为空")


def _flatten_toml(data: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for section in ("tunnel", "ssh", "service"):
        section_data = data.get(section, {})
        if isinstance(section_data, dict):
            flat.update(section_data)
    return flat


def load_config(path: Path | None = None) -> TunnelConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    flat = _flatten_toml(raw)
    known = {field.name for field in fields(TunnelConfig)}
    kwargs = {key: flat[key] for key in known if key in flat}
    config = TunnelConfig(**kwargs)
    config.validate()
    return config


def save_config(config: TunnelConfig, path: Path | None = None) -> Path:
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(render_config_toml(config), encoding="utf-8")
    return config_path


def render_config_toml(config: TunnelConfig) -> str:
    data = asdict(config)
    return "\n".join(
        [
            "# stable-tunnel 配置文件",
            "# 路径: ~/.config/stable-tunnel/config.toml",
            "",
            "[tunnel]",
            f'remote_host = "{data["remote_host"]}"',
            f"remote_port = {data['remote_port']}",
            f'local_host = "{data["local_host"]}"',
            f"local_port = {data['local_port']}",
            f'user = "{data["user"]}"',
            "",
            "[ssh]",
            f"connect_timeout = {data['connect_timeout']}",
            f"server_alive_interval = {data['server_alive_interval']}",
            f"server_alive_count_max = {data['server_alive_count_max']}",
            f"strict_host_key_checking = {'true' if data['strict_host_key_checking'] else 'false'}",
            f"ssh_verbose = {'true' if data['ssh_verbose'] else 'false'}",
            "",
            "[service]",
            f"restart_sec = {data['restart_sec']}",
            f"clean_remote_before_start = {'true' if data['clean_remote_before_start'] else 'false'}",
            f'install_dir = "{data["install_dir"]}"',
            "",
        ]
    )


def merge_cli_overrides(config: TunnelConfig, overrides: dict[str, Any]) -> TunnelConfig:
    data = asdict(config)
    for key, value in overrides.items():
        if value is not None:
            data[key] = value
    merged = TunnelConfig(**data)
    merged.validate()
    return merged
