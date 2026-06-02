from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from stable_tunnel.config import CLEAN_SCRIPT_NAME, TunnelConfig


def _template_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "templates" / name


def render_service_unit(config: TunnelConfig) -> str:
    ssh_options = [
        f"-o ConnectTimeout={config.connect_timeout}",
        f"-o ExitOnForwardFailure=yes",
        f"-o ServerAliveInterval={config.server_alive_interval}",
        f"-o ServerAliveCountMax={config.server_alive_count_max}",
        "-o TCPKeepAlive=yes",
    ]
    if config.strict_host_key_checking:
        ssh_options.append("-o StrictHostKeyChecking=yes")
    else:
        ssh_options.extend(
            ["-o StrictHostKeyChecking=no", "-o UserKnownHostsFile=/dev/null"]
        )

    ssh_prefix = "-v " if config.ssh_verbose else ""
    ssh_cmd = (
        f"/usr/bin/ssh {ssh_prefix}-N {' '.join(ssh_options)} "
        f"-R {config.remote_port}:{config.local_host}:{config.local_port} "
        f"{config.remote_host}"
    )

    lines = [
        "[Unit]",
        (
            "Description=SSH Reverse Tunnel "
            f"Local {config.local_port} to Remote {config.remote_port} via {config.remote_host}"
        ),
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        f"User={config.user}",
    ]

    if config.clean_remote_before_start:
        lines.append(
            "ExecStartPre="
            f"{config.clean_script_path} {config.remote_host} {config.remote_port}"
        )

    lines.extend(
        [
            f"ExecStart={ssh_cmd}",
            "Restart=always",
            f"RestartSec={config.restart_sec}",
            "StartLimitIntervalSec=0",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    return "\n".join(lines)


def _run(cmd: list[str], *, dry_run: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    if dry_run:
        print("[dry-run]", " ".join(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return subprocess.run(cmd, text=True, check=check)


def _sudo_write(content: str, dest: Path, *, mode: int = 0o644, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[dry-run] write {dest} ({len(content)} bytes, mode {oct(mode)})")
        print(content)
        return

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(content)
        temp_path = handle.name

    try:
        _run(["sudo", "install", "-m", oct(mode)[2:], temp_path, str(dest)])
    finally:
        os.unlink(temp_path)


def install_service(config: TunnelConfig, *, dry_run: bool = False) -> None:
    clean_src = _template_path(CLEAN_SCRIPT_NAME)
    unit_content = render_service_unit(config)

    if not dry_run:
        _run(["sudo", "install", "-d", "-m", "755", config.install_dir])
        _run(
            [
                "sudo",
                "install",
                "-m",
                "755",
                str(clean_src),
                str(config.clean_script_path),
            ]
        )

    _sudo_write(unit_content, config.service_unit_path, dry_run=dry_run)
    _run(["sudo", "systemctl", "daemon-reload"], dry_run=dry_run)
    _run(["sudo", "systemctl", "enable", "--now", config.service_unit_name], dry_run=dry_run)


def uninstall_service(config: TunnelConfig, *, dry_run: bool = False) -> None:
    _run(
        ["sudo", "systemctl", "disable", "--now", config.service_unit_name],
        dry_run=dry_run,
        check=False,
    )

    if dry_run:
        print(f"[dry-run] rm {config.service_unit_path}")
        print(f"[dry-run] rm {config.clean_script_path}")
    else:
        if config.service_unit_path.exists():
            _run(["sudo", "rm", "-f", str(config.service_unit_path)])
        if config.clean_script_path.exists():
            _run(["sudo", "rm", "-f", str(config.clean_script_path)])

    _run(["sudo", "systemctl", "daemon-reload"], dry_run=dry_run)


def show_status(config: TunnelConfig) -> int:
    result = subprocess.run(
        ["systemctl", "status", config.service_unit_name],
        text=True,
    )
    print()
    subprocess.run(
        [
            "journalctl",
            "-u",
            config.service_unit_name,
            "-n",
            "20",
            "--no-pager",
        ],
        check=False,
    )
    return result.returncode


def test_tunnel(config: TunnelConfig) -> int:
    print(f"1/2 测试 SSH 连通性: {config.remote_host}")
    ping = subprocess.run(
        [
            "ssh",
            f"-o ConnectTimeout={config.connect_timeout}",
            "-o BatchMode=yes",
            *(["-o StrictHostKeyChecking=yes"] if config.strict_host_key_checking else [
                "-o StrictHostKeyChecking=no",
                "-o UserKnownHostsFile=/dev/null",
            ]),
            config.remote_host,
            "echo ok",
        ],
        text=True,
        capture_output=True,
    )
    if ping.returncode != 0:
        print(ping.stderr or ping.stdout or "SSH 连接失败")
        return ping.returncode
    print("SSH 连通性 OK")

    if not config.clean_remote_before_start:
        print("2/2 跳过远端端口清理测试（clean_remote_before_start=false）")
        return 0

    print(f"2/2 测试远端端口清理: {config.remote_host}:{config.remote_port}")
    clean_script = _template_path(CLEAN_SCRIPT_NAME)
    env = os.environ.copy()
    env["SSH_CONNECT_TIMEOUT"] = str(config.connect_timeout)
    clean = subprocess.run(
        [str(clean_script), config.remote_host, str(config.remote_port)],
        text=True,
        env=env,
    )
    return clean.returncode


def copy_example_config(dest: Path) -> None:
    example = Path(__file__).resolve().parents[1] / "config.example.toml"
    if example.is_file():
        shutil.copy(example, dest)
    else:
        from stable_tunnel.config import save_config

        save_config(
            TunnelConfig(remote_host="your-jump-host", remote_port=10023),
            dest,
        )
