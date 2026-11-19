"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

async function run() {
  const calls = [];
  const window = {};
  const context = vm.createContext({
    window,
    __: String,
    URLSearchParams,
    frappe: {
      call(options) {
        calls.push(options);
        return Promise.resolve({ message: {} });
      },
    },
  });
  vm.runInContext(
    fs.readFileSync(
      path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js",
      ),
      "utf8",
    ),
    context,
  );
  const api = window.AlmdinaPlanWorkspaceAPI;
  const settings = {
    packing_mode: "smart",
    cutting_machine_type: "CNC Router",
    kerf_mm: 3,
    trim_margin_mm: 5,
    optimization_time_limit_sec: 30,
  };
  const original = JSON.stringify(settings);
  await api.preview("DCO-1", settings);
  assert.equal(calls.at(-1).args.record_search_details, 0);
  await api.preview("DCO-1", settings, { recordSearchDetails: true });
  assert.equal(calls.at(-1).args.record_search_details, 1);
  assert.equal(JSON.stringify(settings), original);
  await api.saveSettings("DCO-1", settings);
  assert.equal(calls.at(-1).args.record_search_details, undefined);
  const url = api.searchReportUrl("DCO & رقم", "a".repeat(32), "html");
  const parsed = new URL(url, "https://isolated.test");
  assert.equal(parsed.origin, "https://isolated.test");
  assert.equal(parsed.searchParams.get("order_name"), "DCO & رقم");
  assert.equal(parsed.searchParams.get("format"), "html");
  assert.match(parsed.pathname, /download_cutting_search_report$/);
}
run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
