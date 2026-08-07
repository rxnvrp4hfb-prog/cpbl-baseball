#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT/cpbl-server.pid"
LOG_FILE="$ROOT/cpbl-server.log"
PORT="${PORT:-8787}"
LABEL="com.openclaw.cpbl-live-dashboard"
DOMAIN="gui/$(id -u)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

port_ok() {
  curl -fsS "http://127.0.0.1:$PORT/" >/dev/null 2>&1
}

launchd_loaded() {
  launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
}

launchd_pid() {
  launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/pid = / {print $3; exit}'
}

running_pid() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return 0
    fi
  fi
  return 1
}

case "${1:-start}" in
  start)
    if port_ok; then
      pid="$(launchd_pid || true)"
      echo "CPBL server already running: http://127.0.0.1:$PORT/${pid:+ (pid $pid)}"
      exit 0
    fi
    if [[ -f "$PLIST" ]]; then
      if ! launchd_loaded; then
        launchctl bootstrap "$DOMAIN" "$PLIST"
      fi
      launchctl kickstart -k "$DOMAIN/$LABEL"
      for _ in {1..20}; do
        port_ok && break
        sleep 0.5
      done
      if port_ok; then
        pid="$(launchd_pid || true)"
        echo "CPBL server started by LaunchAgent: http://127.0.0.1:$PORT/${pid:+ (pid $pid)}"
        exit 0
      fi
      echo "LaunchAgent did not start the server. Check: $ROOT/launchd.err.log" >&2
      exit 1
    fi
    if pid="$(running_pid)"; then
      echo "CPBL server already running: http://127.0.0.1:$PORT/ (pid $pid)"
      exit 0
    fi
    cd "$ROOT"
    PORT="$PORT" nohup python3 server.py >> "$LOG_FILE" 2>&1 &
    echo "$!" > "$PID_FILE"
    for _ in {1..20}; do
      if port_ok; then
        break
      fi
      sleep 0.5
    done
    if pid="$(running_pid)" && port_ok; then
      echo "CPBL server started: http://127.0.0.1:$PORT/ (pid $pid)"
      echo "Log: $LOG_FILE"
    else
      echo "CPBL server failed to start. See: $LOG_FILE" >&2
      exit 1
    fi
    ;;
  stop)
    if launchd_loaded; then
      launchctl bootout "$DOMAIN/$LABEL"
      echo "CPBL LaunchAgent stopped."
    elif pid="$(running_pid)"; then
      kill "$pid"
      rm -f "$PID_FILE"
      echo "CPBL server stopped."
    else
      rm -f "$PID_FILE"
      echo "CPBL server is not running."
    fi
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  status)
    if port_ok; then
      pid="$(launchd_pid || running_pid || true)"
      echo "CPBL server running: http://127.0.0.1:$PORT/${pid:+ (pid $pid)}"
    else
      echo "CPBL server is not running."
      exit 1
    fi
    ;;
  log)
    tail -n 80 "$LOG_FILE"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|log}" >&2
    exit 2
    ;;
esac
