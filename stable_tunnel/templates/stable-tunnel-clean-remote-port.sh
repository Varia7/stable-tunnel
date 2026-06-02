#!/usr/bin/env bash
set -Eeuo pipefail

target="${1:?usage: stable-tunnel-clean-remote-port.sh <ssh-target> <remote-port>}"
port="${2:?usage: stable-tunnel-clean-remote-port.sh <ssh-target> <remote-port>}"
connect_timeout="${SSH_CONNECT_TIMEOUT:-3}"

case "${port}" in
  *[!0-9]* | "")
    echo "remote port must be numeric" >&2
    exit 64
    ;;
esac

ssh \
  -o ConnectTimeout="${connect_timeout}" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  "${target}" \
  "REMOTE_PORT='${port}' bash -s" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

port="${REMOTE_PORT:?missing REMOTE_PORT}"
current_user="$(id -un)"

listeners="$(
  ss -H -ltnp "sport = :${port}" 2>/dev/null || true
)"

if [ -z "${listeners}" ]; then
  echo "remote port ${port} is free"
  exit 0
fi

pids="$(
  printf '%s\n' "${listeners}" |
    sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' |
    sort -u
)"

if [ -z "${pids}" ]; then
  echo "remote port ${port} is occupied, but process ids are not visible:"
  printf '%s\n' "${listeners}"
  exit 2
fi

for pid in ${pids}; do
  comm="$(ps -o comm= -p "${pid}" 2>/dev/null | awk '{print $1}')"
  user="$(ps -o user= -p "${pid}" 2>/dev/null | awk '{print $1}')"

  if [ "${comm}" != "sshd" ] || [ "${user}" != "${current_user}" ]; then
    echo "refusing to kill pid ${pid}: comm=${comm:-?} user=${user:-?}"
    printf '%s\n' "${listeners}"
    exit 3
  fi
done

for pid in ${pids}; do
  echo "killing stale remote sshd pid ${pid} on port ${port}"
  kill "${pid}" 2>/dev/null || true
done

sleep 1

if ss -H -ltn "sport = :${port}" | grep -q .; then
  echo "remote port ${port} is still occupied after cleanup"
  ss -ltnp "sport = :${port}" || true
  exit 4
fi

echo "remote port ${port} cleaned"
REMOTE_SCRIPT
