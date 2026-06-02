#!/usr/bin/env python3
"""stable-tunnel CLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stable_tunnel.config import (
    CONFIG_DIR,
    DEFAULT_CONFIG_PATH,
    TunnelConfig,
    load_config,
    merge_cli_overrides,
    save_config,
)
from stable_tunnel.service import (
    copy_example_config,
    install_service,
    show_status,
    test_tunnel,
    uninstall_service,
)


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"配置文件路径（默认: {DEFAULT_CONFIG_PATH}）",
    )
    parser.add_argument("--remote-host", help="SSH 跳板机 Host（~/.ssh/config 中的名称或 user@host）")
    parser.add_argument("--remote-port", type=int, help="远端监听端口")
    parser.add_argument("--local-host", default=None, help="本机转发目标地址（默认 127.0.0.1）")
    parser.add_argument("--local-port", type=int, default=None, help="本机端口（默认 22）")
    parser.add_argument("--user", help="systemd 服务运行用户（默认当前用户）")
    parser.add_argument(
        "--no-clean-remote",
        action="store_true",
        help="启动前不清理远端 stale sshd 占用",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的操作")


def _cli_overrides(args: argparse.Namespace) -> dict:
    overrides = {
        "remote_host": args.remote_host,
        "remote_port": args.remote_port,
        "local_host": args.local_host,
        "local_port": args.local_port,
        "user": args.user,
    }
    if args.no_clean_remote:
        overrides["clean_remote_before_start"] = False
    return overrides


def _resolve_config(args: argparse.Namespace, *, require_complete: bool) -> TunnelConfig:
    overrides = _cli_overrides(args)
    has_cli = any(value is not None for value in overrides.values() if value is not False)

    if args.config.is_file():
        config = load_config(args.config)
        if has_cli:
            config = merge_cli_overrides(config, overrides)
        return config

    if require_complete and (not args.remote_host or args.remote_port is None):
        print(
            "缺少配置：请先创建配置文件，或通过 --remote-host / --remote-port 指定。\n"
            f"  stable-tunnel init\n"
            f"  stable-tunnel install --remote-host HOST --remote-port PORT",
            file=sys.stderr,
        )
        sys.exit(2)

    config = TunnelConfig(
        remote_host=args.remote_host or "your-jump-host",
        remote_port=args.remote_port or 10023,
        local_host=args.local_host or "127.0.0.1",
        local_port=args.local_port or 22,
        user=args.user or "",
        clean_remote_before_start=not args.no_clean_remote,
    )
    if has_cli:
        config = merge_cli_overrides(config, overrides)
    config.validate()
    return config


def cmd_init(args: argparse.Namespace) -> int:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if args.config.exists() and not args.force:
        print(f"配置文件已存在: {args.config}")
        print("使用 --force 覆盖，或直接编辑该文件。")
        return 1

    if args.remote_host and args.remote_port is not None:
        config = TunnelConfig(remote_host=args.remote_host, remote_port=args.remote_port)
        config = merge_cli_overrides(config, _cli_overrides(args))
    else:
        copy_example_config(args.config)
        print(f"已创建示例配置: {args.config}")
        print("请编辑 remote_host / remote_port 后执行 stable-tunnel install")
        return 0

    save_config(config, args.config)
    print(f"已写入配置: {args.config}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    config = _resolve_config(args, require_complete=True)
    save_config(config, args.config)
    print(f"配置: {args.config}")
    print(
        f"隧道: 本机 {config.local_host}:{config.local_port} "
        f"-> 远端 {config.remote_host}:{config.remote_port}"
    )
    print(f"服务: {config.service_unit_name}（system 级）")
    install_service(config, dry_run=args.dry_run)
    if not args.dry_run:
        print()
        print("安装完成。查看状态: stable-tunnel status")
        print(
            f"从跳板机连回本机: 在 {config.remote_host} 上执行 "
            f"ssh -p {config.remote_port} <本机用户名>@127.0.0.1"
        )
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    config = _resolve_config(args, require_complete=False)
    uninstall_service(config, dry_run=args.dry_run)
    if not args.dry_run:
        print("已卸载服务。")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = _resolve_config(args, require_complete=False)
    return show_status(config)


def cmd_test(args: argparse.Namespace) -> int:
    config = _resolve_config(args, require_complete=True)
    return test_tunnel(config)


def cmd_show_config(args: argparse.Namespace) -> int:
    config = _resolve_config(args, require_complete=False)
    print(f"# 配置文件: {args.config}")
    from stable_tunnel.config import render_config_toml

    print(render_config_toml(config))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stable-tunnel",
        description="安装/管理稳定的 SSH 反向隧道 systemd 服务",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="创建默认配置文件")
    init_parser.add_argument("--force", action="store_true", help="覆盖已有配置文件")
    _add_config_args(init_parser)
    init_parser.set_defaults(func=cmd_init)

    install_parser = sub.add_parser("install", help="安装并启动 systemd 服务")
    _add_config_args(install_parser)
    install_parser.set_defaults(func=cmd_install)

    uninstall_parser = sub.add_parser("uninstall", help="停止并移除 systemd 服务")
    _add_config_args(uninstall_parser)
    uninstall_parser.set_defaults(func=cmd_uninstall)

    status_parser = sub.add_parser("status", help="查看服务状态与最近日志")
    _add_config_args(status_parser)
    status_parser.set_defaults(func=cmd_status)

    test_parser = sub.add_parser("test", help="测试 SSH 连通性与远端端口清理")
    _add_config_args(test_parser)
    test_parser.set_defaults(func=cmd_test)

    show_parser = sub.add_parser("show-config", help="显示当前有效配置")
    _add_config_args(show_parser)
    show_parser.set_defaults(func=cmd_show_config)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
