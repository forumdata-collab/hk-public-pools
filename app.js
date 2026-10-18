/* 全港公眾泳池 · 開放狀態 — 前端邏輯（HK 時間即時計算，唔靠伺服器） */
(function () {
  "use strict";
  var D = window.POOLS_DATA || { pools: [], districts: [] };
  var HOL = new Set(D.holidays || []);
  var WD = { "日": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "天": 0 };
  var CN = ["日", "一", "二", "三", "四", "五", "六"];
  var MN = ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"];
  var MN_SHORT = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];
  var STATE = { filter: "all", open: new Set(), html: {}, built: false, wxOpen: false };

  function hkNow() { return new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Hong_Kong" })); }
  function p2(n) { return (n < 10 ? "0" : "") + n; }
  function ymd(d) { return d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate()); }
  function hm(m) { return p2(Math.floor(m / 60)) + ":" + p2(m % 60); }
  function toMin(s) { var a = (s || "").split(":"); return parseInt(a[0], 10) * 60 + parseInt(a[1] || 0, 10); }
  function esc(s) { return (s || "").replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function slug(s) { return "p" + s.replace(/[^\u4e00-\u9fffA-Za-z0-9]/g, "").slice(0, 14) + Math.abs(hash(s)) % 997; }
  function hash(s) { var h = 0; for (var i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0; } return h; }
  var SLUG = {};
  function slugOf(p) { return SLUG[p.name] || (SLUG[p.name] = slug(p.name)); }
  function norm(s) { return (s || "").replace(/[\s()（）．.]/g, ""); }

  /* ── 日期判斷 ── */
  function inMaint(m, now) {
    var y = now.getFullYear(), t = now.getMonth() * 100 + now.getDate();
    var s = (m.startMonth - 1) * 100 + m.startDay, e = (m.endMonth - 1) * 100 + m.endDay;
    if (s <= e) return t >= s && t <= e;
    return t >= s || t <= e; // 跨年（如 11月1日 – 翌年3月31日）
  }
  function weekRange(now) { // 同一星期（星期一至日）
    var dow = now.getDay(), off = (dow === 0 ? 6 : dow - 1);
    var mon = new Date(now.getTime()); mon.setDate(now.getDate() - off);
    return mon;
  }
  function cleaningInfo(cl, now) {
    if (!cl || !cl.day) return null;
    var main = WD[cl.day], fb = cl.fallback ? WD[cl.fallback] : null;
    var mon = weekRange(now);
    var mainDate = new Date(mon.getTime()); mainDate.setDate(mon.getDate() + ((main + 6) % 7));
    var mainHol = HOL.has(ymd(mainDate));
    if (mainHol && fb !== null) {
      var fbDate = new Date(mon.getTime()); fbDate.setDate(mon.getDate() + ((fb + 6) % 7));
      if (!HOL.has(ymd(fbDate)) && now.getDay() === fb) return { on: true, moved: true, day: cl.fallback, why: "本週原定星期" + cl.day + "為公眾假期" };
      return { on: false, moved: true, day: cl.fallback, why: "本週清潔日改為星期" + cl.fallback + "（原定星期" + cl.day + "為公眾假期）" };
    }
    if (now.getDay() === main) return { on: true, moved: false, day: cl.day, why: "" };
    return { on: false, moved: false, day: cl.day, why: "" };
  }
  function annActive(a, now) {
    var s = new Date(a.start.replace("T", " ").replace(/-/g, "/")), e = new Date(a.end.replace("T", " ").replace(/-/g, "/"));
    return now >= s && now <= e;
  }

  /* ── 泳池狀態 ── */
  function statusOf(p, now) {
    var nowM = now.getHours() * 60 + now.getMinutes();
    var mk = MN[now.getMonth()];
    var md = (p.months || {})[mk];
    var sessions = (md && md.sessions && md.sessions.length) ? md.sessions : [];
    var out = { cls: "closed", label: "休館", detail: [], rows: [], suspended: [], anns: [], notes: [] };

    var maintAll = (p.maintenance || []).filter(function (m) { return m.pool === "全場" && inMaint(m, now); });
    var maintSome = (p.maintenance || []).filter(function (m) { return m.pool !== "全場" && inMaint(m, now); });
    var cl = cleaningInfo(p.cleaning, now);
    var anns = (p.announcements || []).filter(function (a) { return annActive(a, now); });
    out.anns = anns;
    anns.forEach(function (a) {
      (a.facilities || []).forEach(function (f) {
        if (/全部設施|所有設施|全場|整個|all facilities/i.test(f)) { out.fullSuspend = true; }
        out.suspended.push(f);
      });
    });

    // 逐節狀態
    var doneAll = true;
    (sessions || []).forEach(function (s) {
      var a = toMin(s.start), b = toMin(s.end), st = "next", txt = "即將開始";
      if (nowM >= b) { st = "over"; txt = "已完結"; }
      else if (nowM >= a) { st = "now"; txt = "進行中"; doneAll = false; }
      else { doneAll = false; }
      out.rows.push({ label: s.label, start: s.start, end: s.end, state: st, text: txt });
    });

    // 先算今日節次本身嘅狀態（開放中／即將開始／休館）
    var base = "closed";
    if (nowM < 300) { base = "closed"; }
    else if (out.rows.some(function (r) { return r.state === "now"; })) { base = "open"; }
    else if (!doneAll) { base = "soon"; }
    var cleanNow = !!(cl && cl.on && sessions.length && nowM >= 600 && nowM < toMin(sessions[Math.min(1, sessions.length - 1)].end));

    // 整體狀態（全場性嘅事優先過節次狀態；休館則蓋過局部通告）
    if (maintAll.length || out.fullSuspend) {
      out.cls = "maint"; out.label = maintAll.length && !out.fullSuspend ? "維修中" : "暫停開放";
      if (maintAll.length) out.detail.push("每年維修工程：" + maintAll.map(rangeText).join("、"));
    } else if (sessions.length === 0) {
      out.cls = "closed"; out.label = "休館";
      out.detail.push("本月份未列入開放時間表（" + mk + "），請看官方頁面確認季節安排。");
    } else if (cleanNow) {
      out.cls = "clean"; out.label = "大清潔中";
      out.detail.push("每周大清潔：上午10:00 至第二節完結，同日第三節重開。");
    } else if (base === "closed") {
      out.cls = "closed"; out.label = "休館";
      if (nowM < 300) out.detail.push("凌晨休館時段：今日首節 " + (sessions.length ? sessions[0].start : "—") + " 開始。");
      else if (out.rows.length) out.detail.push("今日全部時段已完結。");
    } else if (anns.length) {
      out.cls = "limited"; out.label = "部分設施暫停";
      out.detail.push("部分設施暫停開放（見下方通告）。");
    } else if (maintSome.length) {
      out.cls = "limited"; out.label = "部分設施維修";
      out.detail.push("部分設施維修：" + maintSome.map(function (m) { return m.pool + "（" + rangeText(m) + "）"; }).join("、"));
    } else if (base === "open") {
      out.cls = "open"; out.label = "開放中";
    } else {
      out.cls = "soon"; out.label = "即將開始";
    }
    out.base = base;

    // 八號或以上熱帶氣旋警告：康文署設施即會關閉（依「康樂及體育設施使用條件」第 10 條）
    if (tc8in(WX.sum)) {
      out.cls = "closed"; out.label = "天氣關閉";
      out.detail.unshift("八號或以上熱帶氣旋警告信號生效：康文署轄下康樂及體育設施即會關閉；信號取消後如情況許可 2 小時內重開。");
    }

    // 附加說明
    if (cl && cl.on && out.cls !== "clean" && base !== "closed") { out.notes.push({ cls: "clean", txt: "今日為每周大清潔日（上午10:00 至第二節完結，第三節重開）。" }); }
    else if (cl && cl.moved && cl.why) { out.notes.push({ cls: "info", txt: cl.why }); }
    if (maintSome.length) { out.notes.push({ cls: "warn", txt: "每年維修工程（部分設施）：" + maintSome.map(function (m) { return m.pool + " " + rangeText(m); }).join("、") }); }
    (md && md.notes ? md.notes : []).forEach(function (t) { out.notes.push({ cls: "warn", txt: "本月時間表備註：" + t }); });
    return out;
  }
  function rangeText(m) {
    return MN_SHORT[m.startMonth - 1] + m.startDay + "日 – " + (m.nextYear ? "翌年" : "") + MN_SHORT[m.endMonth - 1] + m.endDay + "日";
  }
  function lastUpdatedText() {
    if (!D.generatedAt) return "未知";
    var d = new Date(D.generatedAt.replace("Z", "+00:00"));
    var hk = new Date(d.toLocaleString("en-US", { timeZone: "Asia/Hong_Kong" }));
    return hk.getFullYear() + "-" + p2(hk.getMonth() + 1) + "-" + p2(hk.getDate()) + " " + p2(hk.getHours()) + ":" + p2(hk.getMinutes());
  }


  /* ── 香港天文台 天氣／警告（泳池開放安排相關） ── */
  var WX = { sum: null, read: null, at: null, err: false };
  var WARN_META = {
    TC1: { n: "一號戒備信號", lv: 1 }, TC3: { n: "三號強風信號", lv: 1 },
    WTCSGNL: { n: "熱帶氣旋警告信號", lv: 2, t: 1 },
    TC8NE: { n: "八號東北烈風或暴風信號", lv: 3 }, TC8NW: { n: "八號西北烈風或暴風信號", lv: 3 },
    TC8SE: { n: "八號東南烈風或暴風信號", lv: 3 }, TC8SW: { n: "八號西南烈風或暴風信號", lv: 3 },
    TC9: { n: "九號烈風或暴風風力增強信號", lv: 3 }, TC10: { n: "十號颶風信號", lv: 3 },
    WTS: { n: "雷暴警告", lv: 2 },
    WRAINY: { n: "黃色暴雨警告", lv: 1 }, WRAINR: { n: "紅色暴雨警告", lv: 2 }, WRAINB: { n: "黑色暴雨警告", lv: 3 },
    WFIRE: { n: "火災危險警告", lv: 1, t: 1 }, WFIREY: { n: "火災危險警告（黃色）", lv: 1 }, WFIRER: { n: "火災危險警告（紅色）", lv: 1 },
    WFROST: { n: "霜凍警告", lv: 1 },
    WHOT: { n: "酷熱天氣警告", lv: 1 }, WCOLD: { n: "寒冷天氣警告", lv: 1 },
    WMON: { n: "強烈季候風信號", lv: 1 }, WMSGNL: { n: "強烈季候風信號", lv: 1 }, WL: { n: "山泥傾瀉警告", lv: 2 },
    WFN: { n: "新界北部水浸特別報告", lv: 2 }, WFNTSA: { n: "新界北部水浸特別報告", lv: 2 },
    WTMW: { n: "海嘯警告", lv: 3 }, WT: { n: "海嘯警告", lv: 3 }, WMS: { n: "特別天氣提示", lv: 1 },
    WTCPRE8: { n: "預警八號熱帶氣旋警告信號之特別報告", lv: 2 }
  };
  var IMPACT = "以上安排依康文署公開條文（雷暴警告下泳池開放安排、康樂及體育設施使用條件）；一切以場地即時公佈為準。";

  /* HKO warnsum 格式：頂層屬性 = 警告代號（WTCSGNL／WRAIN／WFIRE／WTS…），
     子類型放喺 .code（TC8NE／WRAINB／WFIREY…）。以前直接用頂層 key 比對子類型 → 八號信號永遠認唔到。 */
  function warnEntries(sum) {
    return Object.keys(sum || {}).map(function (c) {
      var w = sum[c]; if (!w || typeof w !== "object") return null;
      var sub = String(w.code || ""), type = String(w.type || ""), name = String(w.name || "");
      var eff = WARN_META[sub] ? sub : (WARN_META[c] ? c : (sub || c));
      var m = WARN_META[eff];
      var label = m ? (m.n + (m.t && type ? "（" + type + "）" : ""))
                    : (name || c) + (type && name.indexOf(type) < 0 ? "（" + type + "）" : "");
      return { key: c, sub: sub, eff: eff, label: label, lv: m ? m.lv : 1, issue: w.issueTime || "", cancel: /^CANCEL$/i.test(sub) };
    }).filter(function (e) { return e && !e.cancel; }).sort(function (a, b) { return b.lv - a.lv; });
  }
  function tc8in(sum) { return warnEntries(sum).some(function (e) { return /^TC(8|9|10)/.test(e.sub || e.eff); }); }
  function hasCode(sum, re) { return warnEntries(sum).some(function (e) { return re.test(e.key) || re.test(e.sub) || re.test(e.eff); }); }

  function loadWx() {
    var base = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=";
    var bust = "&_=" + Date.now();       // HKO CDN 逐 URL 快取 → 一定要 cache-buster
    Promise.all([
      fetch(base + "warnsum&lang=tc" + bust, { cache: "no-store" }).then(function (r) { return r.json(); }).catch(function () { return null; }),
      fetch(base + "rhrread&lang=tc" + bust, { cache: "no-store" }).then(function (r) { return r.json(); }).catch(function () { return null; })
    ]).then(function (a) {
      WX.sum = a[0] && typeof a[0] === "object" ? a[0] : {};
      WX.read = a[1] || null;
      WX.err = !a[0] && !a[1];
      WX.at = new Date();
      renderWx(); render();
    });
  }

  function renderWx() {
    var bar = document.getElementById("wx");
    if (!bar) return;
    var r = WX.read || {}, sum = WX.sum || {};
    var t = ((r.temperature || {}).data || []).filter(function (x) { return x.place === "香港天文台" || x.place === "京士柏"; })[0];
    var hum = ((r.humidity || {}).data || [])[0];
    var uv = ((r.uvindex || {}).data || [])[0];
    var flood = ((r.rainfall || {}).data || []).filter(function (x) { return (x.max || 0) > 0; });
    var strike = ((((r.lightning || {}).data) || []).filter(function (x) { return String(x.occur) === "true"; })) || [];
    var ws = warnEntries(sum);

    var lv = ws.length ? ws[0].lv : 0;
    var cls = lv >= 3 ? "wx-l3" : (lv === 2 ? "wx-l2" : (lv === 1 ? "wx-l1" : "wx-ok"));
    var strip = document.getElementById("wx-strip"), body = document.getElementById("wx-body");
    if (!strip || !body) return;
    bar.className = "wx-bar " + cls + (STATE.wxOpen ? " open" : "");
    // 簡約一行：警告 / 溫度 / 濕度 / UV / 閃電
    var s = [];
    if (!WX.at && !ws.length) s.push('<span class="w">天文台警告載入中…</span>');
    else if (ws.length) s.push('<span class="w">⚠️ ' + ws.map(function (w) { return esc(w.label); }).join("、") + "</span>");
    else s.push('<span class="w">現時無天文台警告</span>');
    if (t) s.push('<span class="m">' + esc(String(t.value)) + "°C</span>");
    if (hum) s.push('<span class="m hide-sm">濕度 ' + esc(String(hum.value)) + "%</span>");
    if (uv) s.push('<span class="m hide-sm">UV ' + esc(String(uv.value)) + esc(uv.desc ? " " + uv.desc : "") + "</span>");
    if (strike.length) s.push('<span class="m">⚡ ' + strike.map(function (x) { return esc(x.place); }).join("、") + "</span>");
    s.push('<span class="more">' + (STATE.wxOpen ? "收起 ▴" : "詳情 ▾") + "</span>");
    strip.innerHTML = s.join("");
    strip.onclick = function () { STATE.wxOpen = !STATE.wxOpen; renderWx(); };
    // 詳情（撳落才展開）
    var out = [];
    out.push('<div class="r">');
    if (t) out.push("<span>氣溫 " + esc(String(t.value)) + "°C（" + esc(t.place) + "）</span>");
    if (hum) out.push("<span>濕度 " + esc(String(hum.value)) + "%</span>");
    if (uv) out.push("<span>紫外線指數 " + esc(String(uv.value)) + "（" + esc(uv.desc || "") + "）</span>");
    if (flood.length) out.push("<span>有雨地區 " + flood.length + " 個</span>");
    if (strike.length) out.push('<span style="color:#c2410c">⚡ 有閃電報告：' + strike.map(function (x) { return esc(x.place); }).join("、") + "</span>");
    if (r.updateTime) out.push("<span>天文台更新 " + esc(r.updateTime.slice(11, 16)) + "</span>");
    out.push('<a href="https://www.hko.gov.hk/tc/wxinfo/currwx/current.htm" target="_blank" rel="noopener">天文台實時天氣 ↗</a>');
    out.push("</div>");
    if (ws.length) {
      out.push('<div class="note-line"><b>生效警告</b>：' + ws.map(function (w) {
        return esc(w.label) + (w.issue ? " 　發出：" + esc(w.issue.slice(11, 16)) : "");
      }).join("；") + "</div>");
    }
    // 對泳池開放嘅影響（依康文署條文）
    var notes = [];
    if (tc8in(sum)) notes.push("八號或以上熱帶氣旋警告信號生效：康文署轄下康樂及體育設施<b>即會關閉</b>；信號取消後場地職員會盡快返回，如情況許可 2 小時內重開。");
    else if (hasCode(sum, /^TC[13]$/)) notes.push("熱帶氣旋警告（一號／三號）生效：泳池一般照常開放；<b>八號或以上即會關閉</b>。");
    if (hasCode(sum, /^WTS$/)) notes.push("雷暴警告生效：如天文台<b>指明受影響地區</b>，該區室外游泳設施暫停開放；未指明地區時，個別泳池室外設施會在（i）10 公里半徑內有閃電報告、（ii）黃色或以上暴雨警告同時生效、或（iii）現場見閃電／聞頻密雷聲時暫停。<b>室內設施不受影響</b>，情況不再適用時室外設施重開。");
    if (hasCode(sum, /^WRAIN[RB]$/)) notes.push("暴雨警告（紅／黑）生效：露天活動請以場地即時公佈為準；如與雷暴警告同時生效，室外設施會暫停。");
    if (hasCode(sum, /^WFIRE/)) notes.push("火災危險警告對泳池開放無直接影響。");
    if (!notes.length) notes.push("現時沒有直接影響泳池開放嘅警告；如天氣惡劣，場地可即時暫停開放，以官方公佈為準。");
    out.push(notes.map(function (n) { return '<div class="note-line">· ' + n + "</div>"; }).join(""));
    out.push('<div class="wx-src">' + IMPACT + '</div>');
    body.innerHTML = out.join("");
  }

  function wxNoteFor(p) {
    var sum = WX.sum || {};
    if (tc8in(sum)) return { cls: "warn", txt: "八號或以上熱帶氣旋警告信號生效：康文署康樂及體育設施即會關閉。" };
    if (hasCode(sum, /^WTS$/)) {
      var areas = p.facAreas || {};
      var out2 = (p.facilities || []).filter(function (f) { return areas[f] === "outdoor"; });
      var ind = (p.facilities || []).filter(function (f) { return areas[f] === "indoor"; });
      if (out2.length) return { cls: "warn", txt: "雷暴警告生效：室外設施（" + out2.join("、") + "）可能暫停開放；室內設施不受影響。" };
      if (ind.length) return { cls: "info", txt: "雷暴警告生效：本泳池設施屬室內，依康文署安排不受影響。" };
      return { cls: "warn", txt: "雷暴警告生效：室外游泳設施會暫停開放（官網未標示本泳池設施屬室內或戶外，請以場地公佈為準）。" };
    }
    if (hasCode(sum, /^WRAIN[RB]$/)) return { cls: "info", txt: "暴雨警告生效：戶外泳池可能即時暫停，以場地公佈為準。" };
    return null;
  }

  /* ── 渲染 ── */
  var COLORS = { open: "#0f7a52", soon: "#d08a00", done: "#94a3b8", closed: "#3f4a5a", maint: "#c2410c", clean: "#6d28d9", limited: "#a16207" };

  function render() {
    var now = hkNow();
    var pools = D.pools || [];
    document.getElementById("upd").textContent = "資料更新 " + lastUpdatedText();
    var counts = {};
    pools.forEach(function (p) { var s = statusOf(p, now); counts[s.cls] = (counts[s.cls] || 0) + 1; p._st = s; });
    var sum = document.getElementById("sum");
    var order = [["open", "開放中"], ["soon", "即將開始"], ["limited", "部分設施暫停／維修"], ["clean", "大清潔中"], ["maint", "維修／暫停開放"], ["closed", "休館／天氣關閉"]];
    sum.innerHTML = order.map(function (o) {
      return '<div class="s ' + o[0] + '"><b>' + (counts[o[0]] || 0) + "</b><span>" + o[1] + "</span></div>";
    }).join("") + '<div class="s"><b>' + pools.length + "</b><span>全港泳池總數</span></div>";

    // chips
    var chips = document.getElementById("chips");
    var byD = {};
    pools.forEach(function (p) { (byD[p.district] = byD[p.district] || []).push(p); });
    chips.innerHTML = '<button class="chip' + (STATE.filter === "all" ? " on" : "") + '" data-d="all">全部<span class="n">' + pools.length + "</span></button>" +
      (D.districts || []).map(function (d) {
        var k = d.name, n = (byD[k] || []).length;
        var open = (byD[k] || []).filter(function (p) { return p._st.cls === "open"; }).length;
        return '<button class="chip' + (STATE.filter === k ? " on" : "") + '" data-d="' + esc(k) + '">' + esc(k) + '<span class="n">' + open + "/" + n + "</span></button>";
      }).join("");
    Array.prototype.forEach.call(chips.querySelectorAll(".chip"), function (b) {
      b.onclick = function () { STATE.filter = b.dataset.d; render(); };
    });

    // list
    var host = document.getElementById("host");
    host.innerHTML = (D.districts || []).map(function (d) {
      var ps = byD[d.name] || [];
      if (!ps.length) return "";
      var hide = (STATE.filter !== "all" && STATE.filter !== d.name) ? " hidden" : "";
      var open = ps.filter(function (p) { return p._st.cls === "open"; }).length;
      return '<section class="dsec' + hide + '" id="d-' + esc(d.code) + '" data-d="' + esc(d.name) + '">' +
        '<div class="dsec-head"><h3>' + esc(d.name) + '</h3><span class="n">' + esc(d.nameEn || "") + " · " + ps.length + " 個泳池 · 開放中 " + open + "</span></div>" +
        '<div class="grid">' + ps.map(card).join("") + "</div></section>";
    }).join("");

    Array.prototype.forEach.call(host.querySelectorAll(".ann>.hd"), function (h) {
      h.onclick = function () {
        var box = h.parentNode; box.classList.toggle("open");
        if (box.id) STATE.open.has(box.id) ? STATE.open["delete"](box.id) : STATE.open.add(box.id);
      };
    });
    Array.prototype.forEach.call(host.querySelectorAll(".acts a[data-goto]"), function (a) {
      a.onclick = function (e) { e.preventDefault(); var t = document.getElementById(a.dataset.goto); if (t) { t.scrollIntoView({ behavior: "smooth", block: "center" }); } };
    });

    buildMap(byD, now);
    STATE.built = true;
  }

  function card(p) {
    var s = p._st || statusOf(p, hkNow());
    var now = hkNow();
    var mk = MN[now.getMonth()];
    var md = (p.months || {})[mk] || {};
    var liveSess = md.sessions && md.sessions.length ? md.sessions : [];
    var sessions = liveSess.length ? liveSess : (p.sessions || []);
    var refOnly = !liveSess.length && (p.sessions || []).length > 0;
    var rows = s.rows.length ? s.rows : sessions.map(function (x) { return { label: x.label, start: x.start, end: x.end, state: "", text: "" }; });
    var id = slugOf(p);
    var susp = s.suspended.map(norm);
    var facs = (p.facilities || []).map(function (f) {
      var hit = susp.some(function (x) { return x && (norm(f) === x || norm(f).indexOf(x) >= 0 || (f.split("&").some(function (t) { return norm(t) === x; }))); });
      return '<span class="tag"' + (hit ? ' style="background:#fee2e2;border-color:#fca5a5;color:#991b1b"' : "") + ">" + esc(f) + (hit ? "（暫停）" : "") + "</span>";
    }).join("");
    var monthsNote = Object.keys(p.months || {}).filter(function (k) { return (p.months[k].notes || []).length; })
      .map(function (k) { return k + "：" + p.months[k].notes.join("；"); }).join("　");
    var sessRows = rows.map(function (r) {
      var cls = r.state === "now" ? "now" : (r.state === "over" ? "over" : "");
      var rem = "";
      if (r.state === "now") {
        var left = toMin(r.end) - (now.getHours() * 60 + now.getMinutes());
        rem = left > 0 ? "（剩 " + Math.floor(left / 60) + " 小時 " + (left % 60) + " 分）" : "";
      }
      return '<tr class="' + cls + '"><td>' + esc(r.label) + '</td><td>' + esc(r.start) + " – " + esc(r.end) + "</td><td>" + esc(r.text) + rem + "</td></tr>";
    }).join("");
    var anns = (s.anns || []).map(function (a, i) {
      var aid = id + "-a" + i;
      var open = STATE.open.has(aid) ? " open" : "";
      return '<div class="ann' + open + '" id="' + aid + '"><div class="hd"><span>通告：' + esc((a.start || "").slice(0, 10)) + " → " + esc((a.end || "").slice(0, 10)) + "　" + esc((a.reason || "").slice(0, 10)) + '</span><span>詳情 ▾</span></div>' +
        '<div class="bd"><div class="fac">暫停設施：' + esc((a.facilities || []).join("、") || "—") + "</div>" +
        (a.reason ? "<div>原因：" + esc(a.reason) + "</div>" : "") +
        (a.remarks ? '<div style="margin-top:4px;white-space:pre-wrap">' + esc(a.remarks) + "</div>" : "") + "</div></div>";
    }).join("");
    var wxN = wxNoteFor(p);
    var notes = (wxN ? '<div class="note ' + wxN.cls + '">' + esc(wxN.txt) + "</div>" : "") +
      (s.notes || []).map(function (n) { return '<div class="note ' + n.cls + '">' + esc(n.txt) + "</div>"; }).join("");
    var detail = (s.detail || []).map(function (t) { return '<div class="note info">' + esc(t) + "</div>"; }).join("");
    var maintAll = (p.maintenance || []);
    var act = [];
    if (p.geo) act.push('<a href="https://www.google.com/maps/search/?api=1&query=' + p.geo.lat + "," + p.geo.lng + '" target="_blank" rel="noopener">Google 地圖</a>');
    act.push('<a href="' + esc(p.officialUrl) + '" target="_blank" rel="noopener">LCSD 官方頁面</a>');
    act.push('<a href="#" data-goto="' + id + '-map">在地圖看</a>');
    return '<article class="card" id="' + id + '" data-name="' + esc(p.name) + '">' +
      '<h4><span class="badge ' + s.cls + '">' + esc(s.label) + "</span> " + esc(p.name) +
      '<span class="en">' + esc(p.nameEn || "") + "</span></h4>" +
      '<div class="meta"><div><b>地址</b>　' + esc(p.address || "—") + "</div>" +
      (p.phone ? "<div><b>電話</b>　" + esc(p.phone) + "</div>" : "") +
      (p.cleaning ? "<div><b>每周大清潔</b>　" + esc(p.cleaning.raw || ("逢星期" + p.cleaning.day + (p.cleaning.fallback ? "（公眾假期改星期" + p.cleaning.fallback + "）" : ""))) + "　上午10:00 至第二節完結</div>" : "") +
      (maintAll.length ? "<div><b>每年維修工程</b>　" + maintAll.map(function (m) { return esc(m.pool + " " + rangeText(m)); }).join("、") + "</div>" : "") +
      (monthsNote ? "<div><b>時間表備註</b>　" + esc(monthsNote) + "</div>" : "") +
      "</div>" +
      (facs ? '<div class="tags">' + facs + "</div>" : "") +
      (refOnly ? '<div class="note">本月份（' + mk + "）未列入夏季開放時間表，下表為夏季時間表，只供參考。</div>" : "") +
      (sessRows ? '<table class="sess"><thead><tr><th>時段</th><th>時間</th><th>狀態</th></tr></thead><tbody>' + sessRows + "</tbody></table>"
        : '<div class="note">本月份（' + mk + "）未有開放時間表資料。</div>") +
      detail + notes + anns +
      '<div class="acts">' + act.join("") + '</div><span id="' + id + '-map"></span></article>';
  }

  /* ── 地圖 ── */
  var map, layer;
  function buildMap(byD, now) {
    if (typeof L === "undefined") return;
    if (!map) {
      map = L.map("map", { scrollWheelZoom: false, zoomControl: true }).setView([22.36, 114.13], 10.6);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap" }).addTo(map);
    }
    if (layer) { map.removeLayer(layer); }
    layer = L.layerGroup();
    (D.pools || []).forEach(function (p) {
      if (!p.geo) return;
      var s = p._st || statusOf(p, now);
      var hide = (STATE.filter !== "all" && STATE.filter !== p.district);
      var c = COLORS[s.cls] || "#3f4a5a";
      var m = L.circleMarker([p.geo.lat, p.geo.lng], {
        radius: 6, color: "#fff", weight: 1.6, fillColor: c, fillOpacity: hide ? 0.18 : 0.95
      });
      m.bindPopup('<b>' + esc(p.name) + '</b><span class="pill" style="background:' + c + '22;color:' + c + '">' + esc(s.label) + "</span><br>" +
        esc(p.district) + "　" + esc(p.address || "") + "<br>" +
        '<a href="#" onclick="window.__poolsGoto(\'' + slugOf(p) + '\');return false;">查看詳情 ↓</a>');
      m.on("click", function () { window.__poolsGoto(slugOf(p), false); });
      layer.addLayer(m);
    });
    layer.addTo(map);
  }
  window.__poolsGoto = function (id, scroll) {
    var el = document.getElementById(id);
    if (!el) return;
    if (el.closest(".dsec.hidden")) { document.querySelectorAll(".dsec").forEach(function (s) { s.classList.remove("hidden"); }); STATE.filter = "all"; render(); el = document.getElementById(id); }
    document.querySelectorAll(".card.hl").forEach(function (x) { x.classList.remove("hl"); });
    if (el) { el.classList.add("hl"); if (scroll !== false) el.scrollIntoView({ behavior: "smooth", block: "center" }); setTimeout(function () { el.classList.remove("hl"); }, 2600); }
  };

  window.__poolsStatus = statusOf;       // 測試鉤：可用指定時間查詢狀態
  window.__poolsRender = render;

  document.addEventListener("DOMContentLoaded", function () {
    render();
    loadWx();
    setInterval(function () { render(); }, 60000);
    setInterval(function () { loadWx(); }, 300000);      // 天文台警告每 5 分鐘更新
  });
  window.__poolsWx = function (sum, read) { WX.sum = sum || {}; WX.read = read || {}; renderWx(); render(); };  // 測試鉤
})();
