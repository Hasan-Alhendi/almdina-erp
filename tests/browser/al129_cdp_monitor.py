"""Independent, read-only CDP health probe for the AL129 Desk smoke."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websocket


STOP = False
SIMPLE_RENDERER_EXPRESSION = "1 + 1"
RECOVERY_STATE_EXPRESSION = r"""(() => {
  const root = window.AlmdinaDcoRecovery;
  const api = root && root.LocalCheckpoint;
  const frm = window.cur_frm;
  let snapshot = null;
  try {
    snapshot = api && frm && typeof api.snapshot === "function"
      ? api.snapshot(frm) : null;
  } catch (_error) {}
  const discoveryVisible = [...document.querySelectorAll(".modal.show")].some(modal =>
    modal.querySelector('[data-recovery-action="continue"]')
      && modal.querySelector('[data-recovery-action="new"]'));
  const checkpointErrorVisible = Boolean(
    document.querySelector('.dco-recovery-status[data-recovery-state="ERROR"]')
  );
  const isNew = Boolean(frm && typeof frm.is_new === "function" && frm.is_new());
  let initializationState = "not_applicable";
  if (!api) initializationState = "api_unavailable";
  else if (!frm) initializationState = "form_not_ready";
  else if (!isNew) initializationState = "form_is_not_new";
  else if (snapshot) initializationState = "checkpoint_ready";
  else if (discoveryVisible) initializationState = "awaiting_draft_selection";
  else if (checkpointErrorVisible) initializationState = "checkpoint_error_visible";
  else initializationState = "pending_or_not_exposed";
  return {
    local_checkpoint_api: Boolean(api),
    form_ready: Boolean(frm),
    is_new: isNew,
    snapshot_present: Boolean(snapshot),
    discovery_visible: discoveryVisible,
    checkpoint_error_visible: checkpointErrorVisible,
    initialization_state: initializationState,
    initialization_internals_exposed: false
  };
})()"""


def _http_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _cdp_call(
    websocket_url: str,
    command_id: int,
    method: str,
    params: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    connection = websocket.create_connection(
        websocket_url,
        timeout=timeout,
        suppress_origin=True,
        enable_multithread=False,
    )
    try:
        connection.send(json.dumps({"id": command_id, "method": method, "params": params}))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("CDP command deadline")
            connection.settimeout(remaining)
            message = json.loads(connection.recv())
            if message.get("id") != command_id:
                continue
            if "error" in message:
                raise RuntimeError("CDP command rejected")
            result = message.get("result", {})
            return result if isinstance(result, dict) else {}
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _page_target(port: int, host: str) -> dict[str, Any] | None:
    targets = _http_json(f"http://127.0.0.1:{port}/json/list", timeout=0.8)
    for target in targets:
        if target.get("type") != "page":
            continue
        if urlsplit(str(target.get("url", ""))).hostname == host:
            return target
    return None


def _measure(port: int, host: str, sample: int, started: float, final: bool) -> dict[str, Any]:
    record: dict[str, Any] = {
        "sample": sample,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "final": final,
    }
    browser_websocket: str | None = None
    try:
        version = _http_json(f"http://127.0.0.1:{port}/json/version", timeout=0.8)
        browser_websocket = version.get("webSocketDebuggerUrl")
        if not isinstance(browser_websocket, str) or not browser_websocket.startswith(
            "ws://127.0.0.1:"
        ):
            raise RuntimeError("non-loopback browser debugger endpoint")
        command_started = time.monotonic()
        browser_result = _cdp_call(browser_websocket, 1, "Browser.getVersion", {}, timeout=0.8)
        record["browser"] = "responsive"
        record["browser_get_version_ms"] = round((time.monotonic() - command_started) * 1000)
        record["browser_product"] = str(browser_result.get("product", ""))[:48]
    except Exception as error:
        record["browser"] = "unavailable"
        record["browser_error"] = type(error).__name__

    try:
        target = _page_target(port, host)
    except Exception as error:
        record["renderer"] = "target_lookup_failed"
        record["renderer_error"] = type(error).__name__
        record["recovery"] = {"initialization_state": "not_measured"}
        return record
    if target is None:
        record["renderer"] = "page_target_unavailable"
        record["recovery"] = {"initialization_state": "page_target_unavailable"}
        return record

    target_websocket = target.get("webSocketDebuggerUrl")
    if not isinstance(target_websocket, str) or not target_websocket.startswith("ws://127.0.0.1:"):
        record["renderer"] = "non_loopback_debugger_endpoint"
        record["recovery"] = {"initialization_state": "not_measured"}
        return record
    try:
        command_started = time.monotonic()
        renderer_result = _cdp_call(
            target_websocket,
            2,
            "Runtime.evaluate",
            {
                "expression": SIMPLE_RENDERER_EXPRESSION,
                "returnByValue": True,
                "awaitPromise": False,
            },
            timeout=0.8,
        )
        value = renderer_result.get("result", {}).get("value")
        record["renderer"] = "responsive" if value == 2 else "unexpected_result"
        record["renderer_evaluate_ms"] = round((time.monotonic() - command_started) * 1000)
    except Exception as error:
        record["renderer"] = (
            "command_timeout"
            if isinstance(error, TimeoutError)
            or type(error).__name__ == "WebSocketTimeoutException"
            else "command_failed"
        )
        record["renderer_error"] = type(error).__name__
        record["recovery"] = {"initialization_state": "not_measured"}
        return record

    if record["renderer"] == "responsive":
        try:
            command_started = time.monotonic()
            recovery_result = _cdp_call(
                target_websocket,
                3,
                "Runtime.evaluate",
                {
                    "expression": RECOVERY_STATE_EXPRESSION,
                    "returnByValue": True,
                    "awaitPromise": False,
                },
                timeout=0.8,
            )
            record["recovery_evaluate_ms"] = round((time.monotonic() - command_started) * 1000)
            value = recovery_result.get("result", {}).get("value")
            record["recovery"] = value if isinstance(value, dict) else {"state": "unavailable"}
        except Exception as error:
            record["recovery_evaluate"] = "failed"
            record["recovery_error"] = type(error).__name__
            record["recovery"] = {"initialization_state": "not_measured"}
    return record


def _emit(record: dict[str, Any], evidence_path: Path | None, summary_path: Path | None) -> None:
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    print(line, flush=True)
    if evidence_path:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        with evidence_path.open("a", encoding="utf-8") as evidence:
            evidence.write(line + "\n")
    if summary_path:
        recovery = record.get("recovery", {})
        summary_line = (
            f"- CDP sample `{record['sample']}` ({record['elapsed_ms']} ms): "
            f"Browser `{record.get('browser', 'unknown')}`"
            f" ({record.get('browser_get_version_ms', 'n/a')} ms), "
            f"Renderer `{record.get('renderer', 'unknown')}`"
            f" ({record.get('renderer_evaluate_ms', 'n/a')} ms), "
            f"Recovery `{recovery.get('initialization_state', 'unknown')}`; "
            f"snapshot `{recovery.get('snapshot_present', 'n/a')}`.\n"
        )
        with summary_path.open("a", encoding="utf-8") as summary:
            summary.write(summary_line)


def _request_stop(_signum: int, _frame: Any) -> None:
    global STOP
    STOP = True


def _diagnosis(records: list[dict[str, Any]]) -> str:
    browser_ok = sum(record.get("browser") == "responsive" for record in records)
    renderer_timeouts = sum(
        record.get("browser") == "responsive"
        and record.get("renderer") == "command_timeout"
        for record in records
    )
    latest = records[-1] if records else {}
    recovery = latest.get("recovery", {})
    if not records or browser_ok == 0:
        return "browser_or_cdp_unavailable"
    if renderer_timeouts >= 2:
        return "browser_responsive_renderer_evaluation_timed_out"
    if latest.get("renderer") == "responsive" and recovery.get("snapshot_present") is True:
        return "browser_renderer_and_checkpoint_ready"
    if latest.get("renderer") == "responsive":
        return "renderer_responsive_checkpoint_not_ready_or_not_exposed"
    return "insufficient_renderer_samples"


def _emit_final(records: list[dict[str, Any]], summary_path: Path | None) -> None:
    result = {
        "event": "cdp_monitor_final",
        "samples": len(records),
        "browser_responsive_samples": sum(
            record.get("browser") == "responsive" for record in records
        ),
        "renderer_timeout_samples_with_browser_responsive": sum(
            record.get("browser") == "responsive"
            and record.get("renderer") == "command_timeout"
            for record in records
        ),
        "diagnosis": _diagnosis(records),
        "last_renderer": records[-1].get("renderer") if records else None,
        "last_recovery_state": (
            records[-1].get("recovery", {}).get("initialization_state")
            if records
            else None
        ),
        "last_snapshot_present": (
            records[-1].get("recovery", {}).get("snapshot_present") if records else None
        ),
    }
    print(json.dumps(result, sort_keys=True), flush=True)
    if summary_path:
        with summary_path.open("a", encoding="utf-8") as summary:
            summary.write(
                "\n- CDP monitor result: `"
                f"{result['diagnosis']}`; samples `{result['samples']}`, "
                f"browser responsive `{result['browser_responsive_samples']}`, "
                "renderer timeouts while browser responsive `"
                f"{result['renderer_timeout_samples_with_browser_responsive']}`, "
                f"latest Recovery `{result['last_recovery_state']}`, "
                f"snapshot `{result['last_snapshot_present']}`.\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--interval", type=float, default=0.4)
    parser.add_argument("--duration", type=float, default=50)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    args = parser.parse_args()
    if args.target_host in {"", "localhost", "127.0.0.1"}:
        raise SystemExit("A specific Desk host is required for target isolation.")

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    summary_value = os.environ.get("GITHUB_STEP_SUMMARY")
    summary_path = Path(summary_value) if summary_value else None
    try:
        args.evidence_file.unlink(missing_ok=True)
    except OSError:
        pass

    started = time.monotonic()
    deadline = started + args.duration
    sample = 0
    records: list[dict[str, Any]] = []
    while time.monotonic() < deadline and not STOP:
        sample += 1
        final = args.stop_file.exists()
        record = _measure(args.port, args.target_host, sample, started, final)
        records.append(record)
        _emit(record, args.evidence_file, summary_path)
        if final:
            break
        next_sample = min(deadline, time.monotonic() + max(args.interval, 0.1))
        while time.monotonic() < next_sample and not STOP:
            if args.stop_file.exists():
                break
            time.sleep(min(0.05, next_sample - time.monotonic()))
    _emit_final(records, summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
