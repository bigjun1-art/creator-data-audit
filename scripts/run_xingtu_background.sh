#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR=""
TIMEOUT=900
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) RUN_DIR="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    --help) echo "usage: run_xingtu_background.sh --run-dir RUN [--timeout SECONDS]"; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$RUN_DIR" && -d "$RUN_DIR" ]] || { echo "ERROR: valid --run-dir is required" >&2; exit 2; }
[[ "$TIMEOUT" =~ ^[0-9]+$ ]] || { echo "ERROR: --timeout must be an integer" >&2; exit 2; }
RUN_DIR="$(cd "$RUN_DIR" && pwd)"
RUNNER="$RUN_DIR/xingtu-page-runner.js"
CAPTURE="$RUN_DIR/xingtu-capture.json"
[[ -f "$RUNNER" ]] || { echo "ERROR: missing $RUNNER" >&2; exit 1; }

STAMP="$(date +%Y%m%d%H%M%S)-$$"
DOWNLOAD_NAME="creator-audit-$STAMP-xingtu-capture.json"
DOWNLOAD_DIR="${CREATOR_AUDIT_DOWNLOAD_DIR:-${HOME}/Downloads}"
DOWNLOADED="$DOWNLOAD_DIR/$DOWNLOAD_NAME"
[[ -d "$DOWNLOAD_DIR" ]] || { echo "ERROR: download directory not found: $DOWNLOAD_DIR" >&2; exit 1; }
TEMP_RUNNER="$(mktemp /private/tmp/creator-audit-xingtu.XXXXXX.js)"
trap 'rm -f "$TEMP_RUNNER"' EXIT
node "$SCRIPT_DIR/build_xingtu_background_runner.mjs" "$RUNNER" "$TEMP_RUNNER" "$DOWNLOAD_NAME" >/dev/null
CODE_B64=$(base64 -i "$TEMP_RUNNER" | tr -d '\n')
EVAL_CODE="eval(new TextDecoder().decode(Uint8Array.from(atob('$CODE_B64'),c=>c.charCodeAt(0))))"

START_RESULT=$(/usr/bin/osascript <<EOF
tell application "Google Chrome"
  set targetCount to 0
  set targetTab to missing value
  repeat with w from 1 to count of windows
    repeat with t from 1 to count of tabs of window w
      set tabURL to URL of tab t of window w
      if tabURL starts with "https://www.xingtu.cn/ad/creator/" then
        set targetCount to targetCount + 1
        set targetTab to tab t of window w
      end if
    end repeat
  end repeat
  if targetCount is 0 then return "ERROR: logged-in Xingtu creator tab not found"
  if targetCount is not 1 then return "ERROR: Xingtu creator tab is not unique; count=" & targetCount
  try
    execute targetTab javascript "$EVAL_CODE"
    return "STARTED"
  on error errMsg
    return "ERROR: injection failed - " & errMsg
  end try
end tell
EOF
)
[[ "$START_RESULT" == "STARTED" ]] || { echo "$START_RESULT" >&2; exit 1; }

for _ in $(seq 1 "$TIMEOUT"); do
  if [[ -s "$DOWNLOADED" ]]; then
    cp "$DOWNLOADED" "$CAPTURE"
    python3 -c 'import json,sys,pathlib; p=pathlib.Path(sys.argv[1]); d=json.load(open(p)); s={"ok":True,"total":len(d.get("results",[])),"verified":len(d.get("completed_ids",[])),"ambiguous":len(d.get("ambiguous_ids",[])),"failed":len(d.get("failed_ids",[])),"capture":str(p),"ability_error":""}; (p.parent/"browser-result.json").write_text(json.dumps(s,ensure_ascii=False,indent=2)); print(json.dumps(s,ensure_ascii=False))' "$CAPTURE"
    exit 0
  fi
  sleep 1
done
echo "ERROR: timed out waiting for $DOWNLOAD_NAME" >&2
exit 1
