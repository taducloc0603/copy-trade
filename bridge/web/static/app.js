// Dashboard. KHONG co chuoi tieng Viet nao trong file nay: moi nhan den tu /api, lay tu
// bridge/labels_vi.py (D-16). Kiem duoc bang mot phep grep, va do la diem cua quy tac.
"use strict";

let UI = {};
const $ = (id) => document.getElementById(id);

function dat(id, chu) { const e = $(id); if (e) e.textContent = chu || ""; }

function veThanhTrangThai(s) {
  dat("app-title", UI.app_title);
  const badge = $("run-mode");
  badge.textContent = s.run_mode_label;
  badge.className = "badge " + (s.run_mode === "RUNNING" ? "chay"
                              : s.run_mode === "PAUSED" ? "dung" : "");
  $("agents").innerHTML = "";
  for (const a of s.agents) {
    const el = document.createElement("span");
    el.className = "agent " + a.status.toLowerCase();
    let chu = a.agent_id + ": " + a.status_label;
    // Clicker ONLINE nhung canary da cu la dau hieu sap hong — dung loai trang thai
    // "trong van khoe" ma broker_connected sinh ra de bat (D-25).
    if (a.role === "CLICKER") {
      chu += " · " + a.canary_label + ": " + (a.canary_at || a.canary_never);
    }
    const cham = document.createElement("span");
    cham.className = "cham";
    el.append(cham, document.createTextNode(chu));
    $("agents").appendChild(el);
  }
}

function veChiSo(m) {
  const ms = (v) => (v === null || v === undefined ? "—" : v + " ms");
  const o = (nhan, giaTri, bao) => {
    const d = document.createElement("div");
    d.className = "o" + (bao ? " bao-dong" : "");
    const n = document.createElement("div");
    n.className = "nhan";
    n.textContent = nhan;
    const g = document.createElement("div");
    g.className = "gia-tri";
    g.textContent = giaTri;
    d.append(n, g);
    return d;
  };
  const el = $("chi-so");
  el.innerHTML = "";
  el.append(o(m.p50_label, ms(m.p50)), o(m.p95_label, ms(m.p95)),
            o(m.hedged_label, m.hedged),
            o(m.attention_label, m.attention, m.attention_alarm));
}

function veBangCap(pairs) {
  dat("tieu-de-cap", UI.pairs_title);
  const dau = $("dau-bang");
  dau.innerHTML = "";
  for (const h of [UI.col_pair, UI.col_symbol, UI.col_direction, UI.col_volume,
                   UI.col_status]) {
    const th = document.createElement("th");
    th.textContent = h;
    dau.appendChild(th);
  }
  const tbody = $("bang-cap").querySelector("tbody");
  tbody.innerHTML = "";
  if (!pairs.length) {
    const tr = tbody.insertRow();
    const td = tr.insertCell();
    td.colSpan = 5;
    td.className = "trong";
    td.textContent = UI.no_pairs;
    return;
  }
  for (const p of pairs) {
    const tr = tbody.insertRow();
    tr.className = (p.attention ? "can-can-thiep " : "") + (p.reason_mismatch ? "sai-kenh" : "");
    for (const v of [p.pair_short, p.symbol, p.direction, p.volume]) {
      tr.insertCell().textContent = v;
    }
    const td = tr.insertCell();
    td.textContent = p.status_label;
    if (p.reason_mismatch) {
      const s = document.createElement("span");
      s.className = "canh-bao-nho";
      s.textContent = p.reason_mismatch_label;
      td.appendChild(s);
    }
  }
}

function veNutDieuKhien() {
  dat("nut-pause-new", UI.btn_pause_new);
  dat("nut-stop-sync", UI.btn_stop_sync);
  dat("nut-resume", UI.btn_resume);
  dat("nut-emergency", UI.btn_emergency);
  const ten = { "tong-quan": UI.nav_main, "sai-lech": UI.nav_findings,
                "cau-hinh": UI.nav_config, "nhat-ky": UI.nav_log };
  document.querySelectorAll(".tab").forEach((t) => { t.textContent = ten[t.dataset.man]; });
}

async function goi(duong, tuy) {
  const r = await fetch(duong, Object.assign(
    { headers: { "content-type": "application/json" } }, tuy || {}));
  let data = {};
  try { data = await r.json(); } catch (e) { data = {}; }
  return { ok: r.ok, data: data };
}

// -- hop xac nhan --------------------------------------------------------------------------
// Ma sat tang dan theo muc nguy hiem: bam thang / hop xac nhan / bat go tay chuoi.
function hoiXacNhan(loi, cumTuBatBuoc) {
  return new Promise((giai) => {
    const d = $("hop-xac-nhan");
    $("xac-nhan-loi").textContent = loi;
    const o = $("xac-nhan-go");
    o.style.display = cumTuBatBuoc ? "block" : "none";
    o.value = "";
    dat("xac-nhan-huy", "✕");
    dat("xac-nhan-ok", "✓");
    const xong = (kq) => { d.close(); giai(kq); };
    $("xac-nhan-huy").onclick = () => xong(null);
    $("xac-nhan-ok").onclick = () => xong(cumTuBatBuoc ? o.value : true);
    d.showModal();
  });
}

// -- man sai lech --------------------------------------------------------------------------

function veBangChung(bc) {
  const box = document.createElement("div");
  box.className = "bang-chung";
  const o = (nhan, giaTri) => {
    const d = document.createElement("div");
    const n = document.createElement("div");
    n.className = "nhan";
    n.textContent = nhan;
    const pre = document.createElement("pre");
    pre.textContent = (giaTri === null || giaTri === undefined)
      ? "—" : JSON.stringify(giaTri, null, 1);
    d.append(n, pre);
    return d;
  };
  box.append(o(bc.db_label, bc.db), o(bc.master_label, bc.master),
             o(bc.client_label, bc.client));
  return box;
}

function veNhom(el, nhan, ds, choPhepHangLoat) {
  el.innerHTML = "";
  if (!ds.length) return;
  const box = document.createElement("div");
  box.className = "sai-lech-nhom";
  const h = document.createElement("h3");
  h.textContent = nhan;
  box.appendChild(h);
  for (const f of ds) {
    const d = document.createElement("div");
    d.className = "dong-sai-lech";
    const tieu = document.createElement("div");
    tieu.textContent = f.kind + " · " + (f.pair_id || "") + " · " + f.suggested_action;
    d.append(tieu, veBangChung(f.evidence));

    const nutOk = document.createElement("button");
    nutOk.textContent = UI.btn_accept;
    nutOk.onclick = async () => {
      // Bridge tu choi finding cu (tinh trang cap da doi). Im lang o day thi nguoi bam tuong da
      // xong, trong khi finding van nam nguyen do.
      const r = await goi("/api/findings/" + f.id + "/accept", { method: "POST" });
      if (!r.data.ok) window.alert(UI.accept_refused);
      taiSaiLech();
    };
    // Bo qua la hanh dong CHO TUNG DONG, va moi dong bi bo qua de lai mot alert ton tai.
    // Khong co nut bo qua hang loat: do la cach mat tien am tham nhat.
    const nutBo = document.createElement("button");
    nutBo.textContent = UI.btn_skip;
    nutBo.onclick = async () => {
      const note = prompt(UI.skip_note_prompt);
      if (!note) return;
      await goi("/api/findings/" + f.id + "/skip", {
        method: "POST", body: JSON.stringify({ note: note }) });
      taiSaiLech();
    };
    d.append(nutOk, nutBo);
    box.appendChild(d);
  }
  if (choPhepHangLoat) {
    const b = document.createElement("button");
    b.textContent = UI.btn_accept_all_safe;
    b.onclick = async () => {
      await goi("/api/findings/accept_all_safe", { method: "POST" });
      taiSaiLech();
    };
    box.appendChild(b);
  }
  el.appendChild(box);
}

async function taiSaiLech() {
  const r = await goi("/api/findings");
  UI = r.data.ui || UI;
  dat("tieu-de-sai-lech", UI.findings_title);
  veNhom($("nhom-safe"), r.data.safe_label, r.data.safe, true);
  veNhom($("nhom-decision"), r.data.decision_label, r.data.decision, false);
  $("khong-sai-lech").textContent = r.data.tong ? "" : UI.no_findings;
}

async function taiNhatKy() {
  const r = await goi("/api/alerts");
  UI = r.data.ui || UI;
  dat("tieu-de-nhat-ky", UI.log_title);
  const el = $("danh-sach-alert");
  el.innerHTML = "";
  if (!r.data.alerts.length) {
    const p = document.createElement("p");
    p.className = "trong";
    p.textContent = UI.no_alerts;
    el.appendChild(p);
    return;
  }
  for (const a of r.data.alerts) {
    const d = document.createElement("div");
    d.className = "dong-sai-lech";
    const t = document.createElement("div");
    t.textContent = a.level_label + " · " + a.code + " · " + a.created_at;
    const m = document.createElement("div");
    m.textContent = a.message;
    const b = document.createElement("button");
    b.textContent = UI.btn_ack;
    b.onclick = async () => {
      await goi("/api/alerts/" + a.id + "/ack", { method: "POST" });
      taiNhatKy();
    };
    d.append(t, m, b);
    el.appendChild(d);
  }
}

async function taiCauHinh() {
  const r = await goi("/api/config");
  UI = r.data.ui || UI;
  dat("tieu-de-cau-hinh", UI.cfg_title);
  const el = $("noi-dung-cau-hinh");
  el.innerHTML = "";
  for (const c of r.data.clients) {
    const d = document.createElement("div");
    d.className = "dong-sai-lech";
    const them = (chu, lop) => {
      const x = document.createElement("div");
      if (lop) x.className = lop;
      x.textContent = chu;
      d.appendChild(x);
      return x;
    };
    them(c.client_id);
    // "Master dong thi Client dong" hien dang CHU, khong phai nut gat: FR-13 noi day la chuc
    // nang bat buoc, va thu khong duoc phep tat thi khong nen trong giong thu tat duoc.
    them(UI.cfg_master_close_always);
    them(UI.cfg_multiplier + ": " + c.volume_multiplier);
    them(UI.cfg_effect_next_open, "canh-bao-nho");
    const pre = document.createElement("pre");
    pre.textContent = (r.data.preview || []).join("\n");
    them(UI.cfg_preview + ":").appendChild(pre);
    them(UI.cfg_open_route + ": " + c.open_route);
    them(UI.cfg_close_route + ": " + c.close_route);
    them(UI.cfg_can_close_master + ": " + (c.can_close_master ? "1" : "0"));
    el.appendChild(d);
  }
  const m = document.createElement("div");
  m.className = "sai-lech-nhom";
  const h = document.createElement("h3");
  h.textContent = UI.map_title;
  m.appendChild(h);
  for (const x of r.data.symbol_maps) {
    const d = document.createElement("div");
    d.className = "dong-sai-lech";
    d.textContent = x.master_symbol + " → " + x.client_symbol;
    if (!x.verified_at) {
      const w = document.createElement("div");
      w.className = "loi";
      w.textContent = UI.map_unverified;
      d.appendChild(w);
    }
    m.appendChild(d);
  }
  el.appendChild(m);
}

// -- vong day thoi gian thuc ------------------------------------------------------------------

function veTatCa(s) {
  UI = s.ui;
  veThanhTrangThai(s.status);
  veChiSo(s.metrics);
  veBangCap(s.pairs);
  veNutDieuKhien();
  $("dong-ho").textContent = new Date().toLocaleTimeString("vi-VN");
  window.soSaiLech = s.findings_count;
}

function moWebSocket() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss" : "ws") +
                           "://" + location.host + "/ws");
  ws.onmessage = (e) => veTatCa(JSON.parse(e.data));
  ws.onclose = () => setTimeout(moWebSocket, 2000);
}

document.addEventListener("DOMContentLoaded", async () => {
  const r = await goi("/api/snapshot");
  veTatCa(r.data);
  moWebSocket();

  document.querySelectorAll(".tab").forEach((t) => {
    t.onclick = () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".man").forEach((x) => x.classList.add("an"));
      t.classList.add("active");
      $(t.dataset.man).classList.remove("an");
      if (t.dataset.man === "sai-lech") taiSaiLech();
      if (t.dataset.man === "nhat-ky") taiNhatKy();
      if (t.dataset.man === "cau-hinh") taiCauHinh();
    };
  });

  const doiMode = (mode) => goi("/api/run_mode", {
    method: "POST", body: JSON.stringify({ mode: mode }) });

  $("nut-pause-new").onclick = () => doiMode("PAUSE_NEW_ENTRIES");   // vo hai, hoan tac duoc
  $("nut-stop-sync").onclick = async () => {
    if (await hoiXacNhan(UI.confirm_stop_sync, null)) doiMode("PAUSED");
  };
  // Cho bam ke ca khi con sai lech, nhung bat nhin thang vao cai minh dang bo lai.
  // Khoa nut thi nguoi ta se di tim cach lach.
  $("nut-resume").onclick = async () => {
    if (window.soSaiLech > 0) {
      const loi = UI.confirm_resume_with_findings.replace("{n}", window.soSaiLech);
      if (!(await hoiXacNhan(loi, null))) return;
    }
    doiMode("RUNNING");
  };
  $("nut-emergency").onclick = async () => {
    const go = await hoiXacNhan(
      UI.confirm_emergency + " " + UI.emergency_phrase, UI.emergency_phrase);
    if (go === null) return;
    const r2 = await goi("/api/emergency", {
      method: "POST", body: JSON.stringify({ phrase: go }) });
    if (!r2.ok) alert(r2.data.message || UI.emergency_wrong);
  };
});
