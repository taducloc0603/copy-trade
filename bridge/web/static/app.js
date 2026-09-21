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

    // Sai lech nao can dong (hoac mo) mot vi the THAT thi dashboard khong lam: no chi sua so
    // sach. Nguoi dung dong tay trong MT5 roi quay lai bam Bo qua kem ghi chu (D-34).
    let nutOk = null;
    if (f.cham_mt5) {
      d.appendChild(nhan(UI.finding_lam_o_mt5, "canh-bao-nho"));
    } else {
      nutOk = document.createElement("button");
      nutOk.textContent = UI.btn_accept;
      nutOk.onclick = async () => {
        // Bridge tu choi finding cu (tinh trang cap da doi). Im lang o day thi nguoi bam tuong da
        // xong, trong khi finding van nam nguyen do.
        const r = await goi("/api/findings/" + f.id + "/accept", { method: "POST" });
        if (!r.data.ok) window.alert(r.data.message || UI.accept_refused);
        taiSaiLech();
      };
    }
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
    if (nutOk) d.appendChild(nutOk);
    d.appendChild(nutBo);
    box.appendChild(d);
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

// -- man cau hinh ---------------------------------------------------------------------------
// Trang nay SUA duoc (D-32). Moi rang buoc nam o bridge/ops.py; o day chi gui JSON va hien lai
// cau tra ve. Khong mot phep kiem nghiep vu nao duoc lam o file nay: JS chay tren may nguoi
// dung, nen mot phep kiem chi o day la mot phep kiem co the bo qua.

let CAU_HINH = null;

function nhan(chu, lop) {
  const e = document.createElement("div");
  if (lop) e.className = lop;
  e.textContent = chu || "";
  return e;
}

function tieuDe(chu) {
  const h = document.createElement("h3");
  h.textContent = chu || "";
  return h;
}

function oChon(giaTri, chon) {
  const s = document.createElement("select");
  for (const c of chon) {
    const o = document.createElement("option");
    o.value = c.gia_tri;
    o.textContent = c.nhan;
    if (String(c.gia_tri) === String(giaTri)) o.selected = true;
    s.appendChild(o);
  }
  return s;
}

function oSo(giaTri, buoc) {
  const i = document.createElement("input");
  i.type = "number";
  i.step = buoc || "any";
  i.value = giaTri === null || giaTri === undefined ? "" : giaTri;
  return i;
}

function oChu(giaTri) {
  const i = document.createElement("input");
  i.type = "text";
  i.value = giaTri || "";
  return i;
}

function hang(nhanChu, oDieuKhien) {
  const d = document.createElement("div");
  d.className = "hang-cau-hinh";
  d.append(nhan(nhanChu, "nhan"), oDieuKhien);
  return d;
}

function nut(chu, lop) {
  const b = document.createElement("button");
  b.textContent = chu;
  if (lop) b.className = lop;
  return b;
}

// Moi lan ghi di qua day: mot cho bao loi, mot cho tai lai. Endpoint nao tra {error, message}
// thi hien message do — JS khong tu dung cau nao.
async function ghiCauHinh(duong, than, sauKhiXong) {
  const r = await goi(duong, { method: "POST", body: JSON.stringify(than) });
  if (!r.ok) {
    alert(r.data.message || r.data.error || "");
    return false;
  }
  if (sauKhiXong) sauKhiXong(r.data);
  await taiCauHinh();
  return true;
}

function hienToken(el, token) {
  const box = document.createElement("div");
  box.className = "khoi-cau-hinh token-moi";
  const pre = document.createElement("pre");
  pre.textContent = token;
  const dong = nut(UI.btn_close);
  dong.onclick = () => box.remove();
  box.append(nhan(UI.token_once, "canh-bao-nho"), pre, dong);
  el.prepend(box);
}

// Moi khoi la mot vung LUU RIENG. Dung chung ham nay de khong khoi nao quen vien hay tieu de --
// nhin nham ranh gioi la sua o khoi nay roi bam nut cua khoi kia.
function khoi(nhanTieuDe) {
  const box = document.createElement("div");
  box.className = "khoi-cau-hinh";
  box.appendChild(tieuDe(nhanTieuDe));
  return box;
}

// Chan khoi: nut luu cua CA KHOI, tach khoi noi dung bang mot duong ke.
function chanKhoi(nutLuu, ghiChu) {
  const chan = document.createElement("div");
  chan.className = "chan-khoi";
  chan.appendChild(nutLuu);
  if (ghiChu) chan.appendChild(nhan(ghiChu, "ghi-chu"));
  return chan;
}

function khoiAgent(el) {
  const box = khoi(UI.agent_title);
  const bang = document.createElement("table");
  const dau = bang.createTHead().insertRow();
  for (const h of ["agent_id", UI.agent_role, UI.agent_login, UI.agent_terminal,
                   UI.agent_status, ""]) {
    const th = document.createElement("th");
    th.textContent = h;
    dau.appendChild(th);
  }
  const than = bang.createTBody();
  for (const a of CAU_HINH.agents) {
    const tr = than.insertRow();
    tr.insertCell().textContent = a.agent_id;
    tr.insertCell().textContent = a.role_label;
    // Clicker khai so tai khoan + tieu de cua so ngay o day: hai gia tri nay truoc kia nam trong
    // config.toml tren VPS. Agent khac chi hien so, vi so cua chung den tu chinh terminal MT5.
    if (a.role === "CLICKER") {
      const login = oSo(a.account_login, "1");
      const tieuDe = oChu(a.terminal_title);
      const luu = nut(UI.cfg_save);
      luu.onclick = () => ghiCauHinh("/api/agent/" + encodeURIComponent(a.agent_id) + "/terminal",
                                     { login: parseInt(login.value, 10) || null,
                                       terminal_title: tieuDe.value });
      tr.insertCell().appendChild(login);
      const o = tr.insertCell();
      // O nhap va nut Luu nam CUNG MOT HANG: nut o dong duoi trong nhu mot nut roi, khong thay
      // no thuoc ve o nao. Cau giai thich thi xuong dong duoi, vi no la chu chu khong phai
      // thao tac.
      const hangO = document.createElement("div");
      hangO.className = "o-va-nut";
      hangO.append(tieuDe, luu);
      o.append(hangO, nhan(UI.agent_terminal_hint, "canh-bao-nho"));
    } else {
      tr.insertCell().textContent = a.account_login || "—";
      tr.insertCell().textContent = "";
    }
    tr.insertCell().textContent = a.status_label;
    const b = nut(UI.btn_new_token);
    b.onclick = async () => {
      if (!(await hoiXacNhan(UI.confirm_new_token, null))) return;
      await ghiCauHinh("/api/agent/" + encodeURIComponent(a.agent_id) + "/token", {},
                       (d) => hienToken(el, d.token));
    };
    tr.insertCell().appendChild(b);
  }
  box.appendChild(bang);
  el.appendChild(box);
}

function khoiClient(el) {
  for (const c of CAU_HINH.clients) {
    const box = khoi(UI.cfg_client_title + " " + c.client_id);
    // "Master dong thi Client dong" hien dang CHU, khong phai nut gat: FR-13 noi day la chuc
    // nang bat buoc, va thu khong duoc phep tat thi khong nen trong giong thu tat duoc.
    box.appendChild(nhan(UI.cfg_master_close_always, "canh-bao-nho"));

    const chieu = oChon(c.copy_mode, [{ gia_tri: "SAME", nhan: UI.cfg_same },
                                      { gia_tri: "OPPOSITE", nhan: UI.cfg_opposite }]);
    const heSo = oSo(c.volume_multiplier, "0.01");
    const duongMo = oChon(c.open_route, CAU_HINH.chon_duong);
    const duongDong = oChon(c.close_route, CAU_HINH.chon_duong);
    // Select chu khong phai checkbox: mot o tich nho chi noi duoc "co dau tich hay khong", va
    // nguoi doc phai TU NHO dau tich nghia la gi. Day la cai quyet dinh Master co bi dong theo
    // hay khong, nen trang thai phai doc duoc bang mot lan liec.
    const dongMaster = oChon(c.can_close_master ? "1" : "0",
                             [{ gia_tri: "0", nhan: UI.cfg_close_master_off },
                              { gia_tri: "1", nhan: UI.cfg_close_master_on }]);
    const hoatDong = oChon(c.enabled ? "1" : "0",
                           [{ gia_tri: "1", nhan: UI.cfg_client_on },
                            { gia_tri: "0", nhan: UI.cfg_client_off }]);

    box.append(hang(UI.cfg_client_enabled, hoatDong),
               hang(UI.cfg_copy_mode, chieu), hang(UI.cfg_multiplier, heSo),
               hang(UI.cfg_open_route, duongMo), hang(UI.cfg_close_route, duongDong),
               hang(UI.cfg_can_close_master, dongMaster));

    const xemTruoc = document.createElement("pre");
    // Theo dung Client nay. Dung mot bang chung cho moi Client la noi sai voi Client thu hai --
    // va no con to ra dung, nen khong ai kiem lai.
    xemTruoc.textContent = ((CAU_HINH.preview || {})[c.client_id] || []).join("\n");
    box.append(nhan(UI.cfg_preview + ":"), xemTruoc);

    const luu = nut(UI.cfg_save, "chinh");
    luu.onclick = async () => {
      // Ma sat dat dung cho: hai thay doi nay doi cach he thong hanh xu voi tien, khong phai
      // doi mot con so.
      if (duongMo.value === "UI" && c.open_route !== "UI"
          && !(await hoiXacNhan(UI.confirm_open_route_ui, null))) return;
      if (dongMaster.value === "1" && !c.can_close_master
          && !(await hoiXacNhan(UI.confirm_can_close_master, null))) return;
      if (hoatDong.value === "0" && c.enabled
          && !(await hoiXacNhan(UI.confirm_client_off, null))) return;
      await ghiCauHinh("/api/client/" + encodeURIComponent(c.client_id), {
        copy_mode: chieu.value,
        volume_multiplier: parseFloat(heSo.value),
        open_route: duongMo.value,
        close_route: duongDong.value,
        can_close_master: dongMaster.value === "1",
        enabled: hoatDong.value === "1",
      }, (d) => {
        if (d.dang_mo) {
          alert(UI.cfg_open_pairs_keep.replace("{n}", d.dang_mo));
        }
      });
    };
    // Xoa nam canh Luu chu khong o mot goc rieng: no cung la mot hanh dong cua DUNG khoi nay.
    // Server tu choi xoa khi Client da co cap lenh, nen nut nay khong the lam mat lich su.
    const xoa = nut(UI.btn_delete);
    xoa.onclick = async () => {
      if (!(await hoiXacNhan(UI.confirm_client_delete, null))) return;
      await ghiCauHinh("/api/client/" + encodeURIComponent(c.client_id) + "/delete", {});
    };
    const chan = chanKhoi(luu, UI.cfg_effect_next_open);
    chan.insertBefore(xoa, chan.childNodes[1] || null);
    box.appendChild(chan);
    el.appendChild(box);
  }
  el.appendChild(khoiThemClient());
}

// Them Client moi. Mot Client = mot terminal MT5 rieng + mot agent CLIENT rieng (+ mot clicker
// rieng neu di qua giao dien), nen o day chi tao DONG CAU HINH -- phan con lai van la viec o
// ngoai. Cau `cfg_client_new_hint` noi dung dieu do de khong ai tuong bam xong la co Client chay.
function khoiThemClient() {
  const box = khoi(UI.cfg_client_new);
  box.appendChild(nhan(UI.cfg_client_new_hint, "ghi-chu"));

  const daDung = new Set(CAU_HINH.clients.map((c) => c.agent_id));
  const agentClient = CAU_HINH.agents.filter((a) => a.role === "CLIENT" && !daDung.has(a.agent_id))
    .map((a) => ({ gia_tri: a.agent_id, nhan: a.agent_id }));
  const clickers = CAU_HINH.agents.filter((a) => a.role === "CLICKER")
    .map((a) => ({ gia_tri: a.agent_id, nhan: a.agent_id }));

  const ma = oChu(CAU_HINH.ma_client_goi_y || "");
  const agent = oChon(null, agentClient.length ? agentClient : [{ gia_tri: "", nhan: "—" }]);
  const clicker = oChon(null, [{ gia_tri: "", nhan: "—" }].concat(clickers));
  const duongMo = oChon("UI", CAU_HINH.chon_duong);
  const duongDong = oChon("UI", CAU_HINH.chon_duong);

  box.append(hang(UI.cfg_client_id, ma), hang(UI.cfg_client_agent, agent),
             hang(UI.cfg_client_clicker, clicker),
             hang(UI.cfg_open_route, duongMo), hang(UI.cfg_close_route, duongDong));

  const them = nut(UI.cfg_client_new, "chinh");
  them.onclick = () => ghiCauHinh("/api/client", {
    client_id: ma.value.trim(),
    agent_id: agent.value,
    clicker_agent: clicker.value || null,
    open_route: duongMo.value,
    close_route: duongDong.value,
  });
  box.appendChild(chanKhoi(them));
  return box;
}

function khoiMaster(el) {
  const box = khoi(UI.cfg_master_close_title);
  const clickers = CAU_HINH.agents.filter((a) => a.role === "CLICKER")
    .map((a) => ({ gia_tri: a.agent_id, nhan: a.agent_id }));
  const chonClicker = oChon(CAU_HINH.master.master_clicker_agent_id, [{ gia_tri: "", nhan: "—" }]
    .concat(clickers));
  const duong = oChon(CAU_HINH.master.master_close_route, CAU_HINH.chon_duong);
  box.append(hang(UI.cfg_master_clicker, chonClicker), hang(UI.cfg_master_route, duong));
  const luu = nut(UI.cfg_save, "chinh");
  luu.onclick = async () => {
    if (duong.value === "UI" && CAU_HINH.master.master_close_route !== "UI"
        && !(await hoiXacNhan(UI.confirm_master_close_ui, null))) return;
    await ghiCauHinh("/api/master_close_route", {
      clicker_agent: chonClicker.value || null,
      close_route: duong.value,
    });
  };
  box.appendChild(chanKhoi(luu));
  el.appendChild(box);
}

function khoiAnhXa(el) {
  const box = khoi(UI.map_title);
  for (const x of CAU_HINH.symbol_maps) {
    const d = document.createElement("div");
    d.className = "dong-sai-lech";
    d.append(nhan(x.client_id + " · " + x.master_symbol + " → " + x.client_symbol),
             nhan(x.enabled ? UI.map_enabled : UI.map_disabled, "canh-bao-nho"));
    if (!x.verified_at) d.appendChild(nhan(UI.map_unverified, "loi"));
    const nutDong = document.createElement("div");
    nutDong.className = "o-va-nut";
    if (x.enabled) {
      const b = nut(UI.map_disable);
      b.onclick = async () => {
        if (!(await hoiXacNhan(UI.confirm_map_disable, null))) return;
        await ghiCauHinh("/api/symbol_map/disable",
                         { client_id: x.client_id, master_symbol: x.master_symbol });
      };
      nutDong.appendChild(b);
    }
    // Xoa khac Tat: tat thi dong con do de bat lai, xoa thi khong con dau vet. Cho ca hai nut
    // canh nhau de nguoi dung chon dung cai minh muon, va hop xac nhan noi ro khac biet do.
    const xoa = nut(UI.map_delete);
    xoa.onclick = async () => {
      if (!(await hoiXacNhan(UI.confirm_map_delete, null))) return;
      await ghiCauHinh("/api/symbol_map/delete",
                       { client_id: x.client_id, master_symbol: x.master_symbol });
    };
    nutDong.appendChild(xoa);
    d.appendChild(nutDong);
    box.appendChild(d);
  }

  const chonClient = oChon(null, CAU_HINH.clients.map(
    (c) => ({ gia_tri: c.client_id, nhan: c.client_id })));
  const sMaster = oChu("");
  const sClient = oChu("");
  box.append(hang("client", chonClient), hang(UI.map_master_symbol, sMaster),
             hang(UI.map_client_symbol, sClient));
  const them = nut(UI.map_add, "chinh");
  // Nut nay LUU, va phia server kiem symbol voi san truoc khi luu. Khong co duong nao luu mot
  // anh xa chua kiem: sai ten symbol mot ky tu chi lo ra dung luc co lenh that di qua.
  them.onclick = () => ghiCauHinh("/api/symbol_map", {
    client_id: chonClient.value,
    master_symbol: sMaster.value,
    client_symbol: sClient.value,
  });
  box.appendChild(chanKhoi(them, UI.map_add_hint));
  el.appendChild(box);
}

function khoiHeThong(el) {
  const box = khoi(UI.cfg_system_title);
  // Moi khoa mot nut luu rieng: chung khong lien quan gi toi nhau, va mot nut luu chung se ghi
  // ca nhung khoa nguoi ta chi vo tinh cham vao.
  box.appendChild(nhan(UI.cfg_system_hint, "ghi-chu"));
  for (const k of CAU_HINH.he_thong) {
    const o = k.chon
      ? oChon(k.gia_tri, k.chon.map((v) => ({ gia_tri: v, nhan: v })))
      : oSo(k.gia_tri, "1");
    const luu = nut(UI.cfg_save);
    luu.onclick = () => ghiCauHinh("/api/system_config",
                                   { khoa: k.khoa, gia_tri: o.value });
    const d = document.createElement("div");
    d.className = "hang-cau-hinh";
    d.append(nhan(k.khoa, "nhan"), o, luu);
    box.appendChild(d);
  }
  el.appendChild(box);
}

// Dat lai he thong. Hai nut, hai cum xac nhan KHAC NHAU: mot cai xoa du lieu, cai kia xoa ca
// cau hinh, va nham giua hai cai do la mat cau hinh ma khong dinh mat.
function khoiDatLai(el) {
  const box = khoi(UI.reset_title);
  box.appendChild(nhan(UI.reset_hint, "ghi-chu"));

  const lam = async (kieu, loi, cum) => {
    const go = await hoiXacNhan(loi + " " + cum, cum);
    if (go === null) return;
    const r = await goi("/api/dat_lai",
                        { method: "POST", body: JSON.stringify({ kieu: kieu, phrase: go }) });
    if (!r.ok) { alert(r.data.message || r.data.error || ""); return; }
    alert(UI.reset_done.replace("{ban_sao}", r.data.ban_sao || ""));
    await taiCauHinh();
  };

  const nutDuLieu = nut(UI.btn_reset_data, "nguy-hiem");
  nutDuLieu.onclick = () => lam("lich_su", UI.confirm_reset_data, UI.reset_phrase_data);
  const nutTatCa = nut(UI.btn_reset_all, "nguy-hiem");
  nutTatCa.onclick = () => lam("toan_bo", UI.confirm_reset_all, UI.reset_phrase_all);

  const chan = chanKhoi(nutDuLieu);
  chan.insertBefore(nutTatCa, chan.childNodes[1] || null);
  box.appendChild(chan);
  el.appendChild(box);
}

function khoiFileConfig(el) {
  if (!CAU_HINH.file_config.length) return;
  const box = khoi(UI.cfg_file_title);
  box.appendChild(nhan(UI.cfg_file_restart, "canh-bao-nho"));

  const o = {};
  for (const k of CAU_HINH.file_config) {
    if (k.chi_doc) {
      const d = document.createElement("div");
      d.className = "hang-cau-hinh";
      d.append(nhan(k.khoa, "nhan"), nhan(k.gia_tri), nhan(UI.cfg_file_readonly, "loi"));
      box.appendChild(d);
      continue;
    }
    let dieuKhien;
    if (k.bi_mat) {
      // Gia tri bi mat khong bao gio di ra khoi Bridge, nen o nay luon trong: go de THAY,
      // de trong la giu nguyen. Hien "(da dat)" ben canh de biet dang co gia tri hay chua.
      dieuKhien = document.createElement("input");
      dieuKhien.type = "password";
      dieuKhien.autocomplete = "new-password";
      dieuKhien.placeholder = k.gia_tri || "";
    } else {
      dieuKhien = k.kieu === "int" ? oSo(k.gia_tri, "1") : oChu(k.gia_tri);
    }
    o[k.khoa] = { el: dieuKhien, k: k };
    const d = document.createElement("div");
    d.className = "hang-cau-hinh";
    d.append(nhan(k.khoa, "nhan"), dieuKhien);
    if (k.bi_mat) d.appendChild(nhan(UI.cfg_file_secret_hint, "canh-bao-nho"));
    box.appendChild(d);
  }

  const luu = nut(UI.cfg_save, "chinh");
  luu.onclick = async () => {
    const doi = {};
    for (const khoa in o) {
      const { el: dk, k } = o[khoa];
      const chu = dk.value.trim();
      // Bi mat de trong = giu nguyen. Khoa thuong thi gui nguyen van, ke ca chuoi rong
      // (xoa telegram_chat_id chang han).
      if (k.bi_mat && !chu) continue;
      if (!k.bi_mat && chu === String(k.gia_tri || "")) continue;
      doi[khoa] = k.kieu === "int" ? parseInt(chu, 10) : chu;
    }
    if (!Object.keys(doi).length) return;
    const r = await goi("/api/file_config",
                        { method: "POST", body: JSON.stringify({ doi: doi }) });
    if (!r.ok) { alert(r.data.message || r.data.error || ""); return; }
    alert(UI.cfg_file_saved);
    await taiCauHinh();
  };
  box.appendChild(chanKhoi(luu, UI.cfg_file_restart_short));

  // Vung rieng, duoi duong ke: day la THEM mot khoa moi vao file, khong phai sua khoa dang co.
  // Ten muc do nguoi van hanh dat, nen no khong the nam trong danh sach khoa co san o tren.
  const vungMoi = document.createElement("div");
  vungMoi.className = "vung-phu";
  vungMoi.append(nhan(UI.cfg_clicker_new_title, "nhan"),
                 nhan(UI.cfg_clicker_new_hint, "ghi-chu"));
  const oTen = oChu("");
  oTen.placeholder = "cl02";
  const oToken = document.createElement("input");
  oToken.type = "password";
  oToken.autocomplete = "new-password";
  vungMoi.append(hang(UI.cfg_clicker_new_name, oTen),
                 hang(UI.cfg_clicker_new_token, oToken));
  const luuMoi = nut(UI.cfg_save, "chinh");
  luuMoi.onclick = async () => {
    const ten = oTen.value.trim().toLowerCase();
    const tok = oToken.value.trim();
    if (!ten || !tok) { alert(UI.cfg_clicker_new_missing); return; }
    const doi = {};
    doi["clicker_" + ten + ".token"] = tok;
    const r = await goi("/api/file_config",
                        { method: "POST", body: JSON.stringify({ doi: doi }) });
    if (!r.ok) { alert(r.data.message || r.data.error || ""); return; }
    oToken.value = "";
    alert(UI.cfg_file_saved);
    await taiCauHinh();
  };
  vungMoi.appendChild(chanKhoi(luuMoi, UI.cfg_file_restart_short));
  box.appendChild(vungMoi);
  el.appendChild(box);
}

async function taiCauHinh() {
  const r = await goi("/api/config");
  UI = r.data.ui || UI;
  CAU_HINH = r.data;
  CAU_HINH.chon_duong = [{ gia_tri: "EA", nhan: UI.cfg_route_ea },
                         { gia_tri: "UI", nhan: UI.cfg_route_ui }];
  dat("tieu-de-cau-hinh", UI.cfg_title);
  const el = $("noi-dung-cau-hinh");
  el.innerHTML = "";
  khoiAgent(el);
  khoiClient(el);
  khoiMaster(el);
  khoiAnhXa(el);
  khoiHeThong(el);
  khoiFileConfig(el);
  khoiDatLai(el);
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
});
