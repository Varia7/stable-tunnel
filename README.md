# stable-tunnel

## 这是什么

**stable-tunnel** 在本机与一台可 SSH 登录的跳板机之间，建立并维护一条 **SSH 反向隧道（reverse tunnel）**：

```
本机 :22  ──反向隧道──▶  跳板机 :remote_port  ──▶  外部可连入本机 SSH
```

隧道由 **systemd 托管**：断线自动重连、开机自启；启动前还会清理跳板机上因上次异常退出而残留的 stale `sshd` 监听，避免「端口已被占用」导致隧道起不来。

### 适用场景

| 场景 | 说明 |
|------|------|
| 内网机器暴露 SSH | 工控机、NAS、实验室 PC 无公网 IP，需经跳板机从外网 SSH 回来 |
| 临时远程运维 | 不想改路由器端口映射，在跳板机上占一个端口即可连回本机 |
| 长期稳定回连 | 比手动 `ssh -R` 更可靠：keepalive + 自动重启 + 端口清理 |

---

## 前置条件

- Linux + systemd
- Python 3.11+
- 本机到跳板机已配置 **免密 SSH**（`~/.ssh/config` 中的 Host 名可直接用作 `remote_host`）
- 跳板机 `sshd` 允许反向转发（通常默认 `AllowTcpForwarding yes`）

---

## 安装

```bash
git clone <your-repo-url> stable-tunnel
cd stable-tunnel
pip install .
```

安装后使用 `stable-tunnel` 命令（亦可用 `python setup_tunnel.py`）。

---

## 快速开始

### 1. 创建配置

```bash
stable-tunnel init
# 编辑 ~/.config/stable-tunnel/config.toml
```

或一步指定参数：

```bash
stable-tunnel init --remote-host your-jump-host --remote-port 10023 --user your-user
```

### 2. 测试（可选）

```bash
stable-tunnel test
```

检查 SSH 连通性，以及跳板机目标端口能否安全清理。

### 3. 安装服务

```bash
stable-tunnel install
# 需要 sudo：写入 /etc/systemd/system/ssh-reverse-tunnel.service
#            写入 /usr/local/bin/stable-tunnel-clean-remote-port.sh
```

### 4. 查看状态

```bash
stable-tunnel status
```

### 5. 从跳板机连回本机

在跳板机 `your-jump-host` 上执行（假设本机 SSH 用户为 `your-user`）：

```bash
ssh -p 10023 your-user@127.0.0.1
```

流量路径：跳板机 `127.0.0.1:10023` → 反向隧道 → 本机 `127.0.0.1:22`。

---

## 卸载

```bash
stable-tunnel uninstall
```

停止并删除 systemd 单元与清理脚本；本地配置文件 `~/.config/stable-tunnel/config.toml` 保留。

---

## 配置说明

配置文件默认路径：`~/.config/stable-tunnel/config.toml`

| 字段 | 含义 | 默认 |
|------|------|------|
| `remote_host` | 跳板机 SSH 目标 | 必填 |
| `remote_port` | 跳板机监听端口 | 必填 |
| `local_host` | 本机转发地址 | `127.0.0.1` |
| `local_port` | 本机端口 | `22` |
| `user` | systemd 运行用户 | 当前用户 |
| `connect_timeout` | SSH 连接超时（秒） | `3` |
| `server_alive_interval` | 保活间隔（秒） | `3` |
| `server_alive_count_max` | 保活失败次数后断开 | `2` |
| `strict_host_key_checking` | 是否校验 host key | `false` |
| `clean_remote_before_start` | 启动前清理远端 stale 端口 | `true` |
| `restart_sec` | 重启间隔（秒） | `5` |

CLI 参数可覆盖配置文件，例如：

```bash
stable-tunnel install --remote-host your-jump-host --remote-port 10023
stable-tunnel install --dry-run   # 只打印将要执行的操作
```

查看合并后的有效配置：

```bash
stable-tunnel show-config
```

---

## 命令一览

| 命令 | 说明 |
|------|------|
| `init` | 创建默认配置文件 |
| `install` | 安装并启动 `ssh-reverse-tunnel.service` |
| `uninstall` | 停止并移除服务 |
| `status` | 服务状态 + 最近 20 条日志 |
| `test` | 测试 SSH 与远端端口清理 |
| `show-config` | 打印当前有效配置 |

---

## 故障排查

**服务反复重启**

```bash
journalctl -u ssh-reverse-tunnel -f
```

常见原因：跳板机不可达、端口被其他进程占用、SSH 密钥失效。

**远端端口被占用且清理失败**

清理脚本只会终止 **当前 SSH 用户** 名下、进程名为 `sshd` 的 stale 监听。若端口被其他服务占用，需手动处理或更换 `remote_port`。

**修改配置后**

```bash
stable-tunnel install   # 会重写 unit 并 reload
```

---

## 项目结构

```
stable-tunnel/
├── stable_tunnel/          # Python 包
│   ├── cli.py
│   ├── config.py
│   ├── service.py
│   └── templates/
│       └── stable-tunnel-clean-remote-port.sh
├── config.example.toml
├── setup_tunnel.py         # 兼容入口
├── pyproject.toml
└── README.md
```

服务名固定为 **`ssh-reverse-tunnel.service`**。

## License

MIT — 详见 [LICENSE](LICENSE)。
