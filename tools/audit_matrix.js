#!/usr/bin/env node
/* 全場狀態矩陣審核：用真實 app.js 的 statusOf()，掃 46 池 × 未來 400 日 × 多個時間點。
   正常 = 零輸出（cron watchdog）；有問題才列印並以 exit 1 結束。
   檢查：全場維修 → 必須「維修／暫停」；開放／部分 → 至少一個設施開；兩者唔可以矛盾；
        大清潔窗口合法（10:00–第二節完結 或官網指定時段）且同節次有重疊；設施清單完整。 */
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const BASE = path.join(__dirname, "..");

const sandbox = { console, setTimeout, setInterval: () => 0, clearInterval() {}, Date, JSON, Math, Set, Map, Promise, Intl };
sandbox.window = sandbox;
sandbox.document = {
  addEventListener() {}, getElementById() { return null; }, querySelectorAll() { return []; },
  documentElement: {}, body: {},
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(BASE, "data/pools.js"), "utf8"), sandbox, { filename: "pools.js" });
vm.runInContext(fs.readFileSync(path.join(BASE, "app.js"), "utf8"), sandbox, { filename: "app.js" });

const D = sandbox.POOLS_DATA, statusOf = sandbox.__poolsStatus;
if (!D || !D.pools || !statusOf) { console.log("❌ audit_matrix: 載入 pools.js / app.js 失敗"); process.exit(1); }

const WHOLE = /^(全場|全泳館|全池|整個泳館)$/;
const norm = s => (s || "").replace(/[\s()（）．.]/g, "");
const toMin = s => { const a = (s || "").split(":"); return (+a[0]) * 60 + (+(a[1] || 0)); };
const MN = ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"];
function inMaint(m, d) {
  const t = (d.getMonth() + 1) * 100 + d.getDate();
  const s = m.startMonth * 100 + m.startDay, e = m.endMonth * 100 + m.endDay;
  return s <= e ? (t >= s && t <= e) : (t >= s || t <= e);
}

const problems = new Set();
const TIMES = [8 * 60, 10 * 60 + 30, 14 * 60, 19 * 60];
const START = new Date();
START.setHours(0, 0, 0, 0);

D.pools.forEach(p => {
  const name = p.name;
  if (!p.facilities || !p.facilities.length) problems.add(name + "：冇設施清單");
  let cleaningSeen = false;

  for (let day = 0; day < 400; day++) {
    const base = new Date(START.getTime() + day * 86400000);
    for (const mins of TIMES) {
      const d = new Date(base.getTime()); d.setHours(Math.floor(mins / 60), mins % 60, 0, 0);
      const s = statusOf(p, d);
      const openN = s.facs.filter(f => !f.why.length).length;
      const whole = (p.maintenance || []).some(m => WHOLE.test(norm(m.pool)) && inMaint(m, d));

      if (whole && s.cls !== "maint") problems.add(`${name}：全場維修期內狀態係「${s.label}」（應為維修／暫停）`);
      if (s.cls === "maint" && openN > 0) problems.add(`${name}：報「${s.label}」但有 ${openN} 個設施標開放`);
      if ((s.cls === "open" || s.cls === "soon" || s.cls === "limited") && openN === 0) problems.add(`${name}：報「${s.label}」但零設施開放`);
      if (s.facs.length !== (p.facilities || []).length) problems.add(`${name}：設施狀態數目同設施清單唔一致`);
      if ((s.facUnknown || []).length) problems.add(`${name}：設施對唔上（${s.facUnknown.join("；")}）`);

      if (s.cleanDay) {
        cleaningSeen = true;
        const from = toMin(s.cleanFrom || "10:00"), to = toMin(s.cleanEnd);
        if (!(from < to)) problems.add(`${name}：大清潔窗口異常 ${s.cleanFrom}–${s.cleanEnd}`);
        const ms = (p.months || {})[MN[d.getMonth()]];
        const sess = (ms && ms.sessions) || [];
        if (sess.length && !sess.some(x => toMin(x.end) > from && toMin(x.start) < to)) {
          problems.add(`${name}：大清潔窗口 ${s.cleanFrom}–${s.cleanEnd} 同任何節次都冇重疊`);
        }
      }
    }
  }
  if (!cleaningSeen && p.cleaning && p.cleaning.day) problems.add(name + "：400 日內搵唔到大清潔日（假期改期／季節表有問題？）");
});

if (problems.size) {
  console.log(`❌ 狀態矩陣審核：${problems.size} 項問題`);
  [...problems].slice(0, 30).forEach(x => console.log("  - " + x));
  process.exit(1);
}
process.exit(0);
