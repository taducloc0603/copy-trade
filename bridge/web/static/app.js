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
  const ten = { "tong-quan": UI.nav_main, "huong-dan": UI.nav_guide,
                "sai-lech": UI.nav_findings, "cau-hinh": UI.nav_config,
                "nhat-ky": UI.nav_log };
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

// Khoi "Can lam" nam o DAU tab Cau hinh, truoc moi khoi khac. Mot ban cai xong van co the
// khong copy duoc lenh nao (thieu anh xa symbol, clicker chua khai so tai khoan), va truoc khoi
// nay cach duy nhat de biet la chay kiem-tra.ps1 tren VPS roi tu doi chieu chin muc voi tri nho.
//
// Danh sach trong khong duoc lam khoi bien mat: "khong con viec nao" la thong tin nguoi dung can,
// va mot khoi thi thoang moi xuat hien thi khong ai hoc duoc cho de tim no.
function khoiCanLam(el) {
  const viec = CAU_HINH.can_lam || [];
  const chan = viec.filter((v) => v.muc === "CHAN");
  const box = khoi(UI.can_lam_title + (chan.length ? " (" + chan.length + ")" : ""));
  if (chan.length) box.appendChild(nhan(UI.can_lam_chan_hint, "canh-bao-nho"));

  if (!viec.length) {
    box.appendChild(nhan(UI.can_lam_xong, "ghi-chu"));
    el.appendChild(box);
    return;
  }
  const ds = document.createElement("ul");
  ds.className = "ds-can-lam";
  for (const v of viec) {
    const li = document.createElement("li");
    li.className = v.muc === "CHAN" ? "chan" : "luu-y";
    const the = document.createElement("span");
    the.className = "the-muc";
    the.textContent = v.muc === "CHAN" ? UI.can_lam_muc_chan : UI.can_lam_muc_luu_y;
    li.append(the, document.createTextNode(" " + v.chu));
    ds.appendChild(li);
  }
  box.appendChild(ds);
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

  // Bon o nhap truoc day deu suy duoc tu MOT con so -- so thu tu cua Client. Ma client, ten hai
  // agent, ten muc clicker, ten Scheduled Task: mot quy tac trong ops.ten_theo_client. Hoi tung
  // cai chi tao co hoi dat lech nhau (AG-CLIENT2 voi muc [clicker_cl_02]).
  box.appendChild(nhan(UI.cfg_client_new_ma.replace("{ma}", CAU_HINH.ma_client_goi_y || ""),
                       "canh-bao-nho"));

  const them = nut(UI.cfg_client_new, "chinh");
  them.onclick = async () => {
    if (!(await hoiXacNhan(UI.confirm_client_new, null))) return;
    const r = await goi("/api/client_moi", { method: "POST" });
    // Mot alert RONG la bao cao loi te nhat co the: no noi "co gi do sai" va het. Loi 500 tra ve
    // text/plain nen `r.data` khong co truong nao -- phai co cau du phong.
    if (!r.ok) { alert(r.data.message || r.data.error || UI.loi_khong_ro); return; }
    // Ve SAU khi dung lai ca tab, khong truoc: `taiCauHinh` xoa sach `noi-dung-cau-hinh` roi ve
    // lai tu dau, nen ve truoc la token hien duoc dung mot nhip roi bi chinh minh xoa -- ma token
    // nay khong doc lai duoc o dau nua.
    await taiCauHinh();
    veClientMoi(r.data);
  };
  box.appendChild(chanKhoi(them));
  return box;
}

// Ket qua cua mot lan them Client. Hai thu phai lam tay, va ca hai deu nam NGOAI trinh duyet:
// dan token vao EA, va dang ky Scheduled Task (can quyen Administrator tren VPS).
function veClientMoi(d) {
  const box = khoi(UI.cfg_client_new_done.replace("{ma}", d.client_id));
  box.className += " token-moi";
  box.appendChild(nhan(UI.cfg_client_new_agent.replace("{agent}", d.agent)
                                              .replace("{clicker}", d.clicker), "ghi-chu"));
  box.appendChild(nhan(UI.cfg_client_new_token, "canh-bao-nho"));
  const ma = document.createElement("pre");
  ma.className = "lenh";
  ma.textContent = d.token_ea;
  box.appendChild(ma);
  box.appendChild(nhan(UI.cfg_client_new_task, "canh-bao-nho"));
  const lenh = document.createElement("pre");
  lenh.className = "lenh";
  lenh.textContent = d.lenh_tac_vu;
  box.appendChild(lenh);
  // Len DAU tab: day la thu duy nhat vua xay ra, va hai viec trong do phai lam ngay.
  const el = $("noi-dung-cau-hinh");
  el.insertBefore(box, el.firstChild);
  box.scrollIntoView({ block: "start" });
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

  // Hai o go tay thanh hai danh sach THAT, lay tu symbol_spec ma EA day len. Go tay o day hong
  // theo kieu te nhat: sai mot ky tu thi khong co loi nao, chi la moi lenh Master bi bo qua
  // trong im lang. Chua co EA nao noi thi danh sach rong -> quay ve o go tay lam duong lui.
  const dsMaster = (CAU_HINH.symbol_master || []).map((x) => x.symbol);
  const dsClient = (CAU_HINH.symbol_client || {});
  const veChon = (ds, hienTai) => oChon(hienTai,
    ds.map((s) => ({ gia_tri: s, nhan: s })));
  const coDanhSach = dsMaster.length > 0;
  const sMaster = coDanhSach ? veChon(dsMaster, null) : oChu("");
  const sClient = oChu("");

  // O phia Client di theo Client dang chon; doi Client thi doi ca danh sach.
  const veOClient = () => {
    const ds = dsClient[chonClient.value] || [];
    const moi = ds.length ? veChon(ds.map((x) => x.symbol), sClient.value) : oChu(sClient.value);
    sClient.replaceWith(moi);
    return moi;
  };

  box.append(hang(UI.map_client, chonClient), hang(UI.map_master_symbol, sMaster),
             hang(UI.map_client_symbol, sClient));
  let oClient = veOClient();
  chonClient.onchange = () => { oClient = veOClient(); veDeXuat(); };

  // De xuat, khong tu tao: chon sai symbol khong bao loi, no chi copy sang mot thi truong khac.
  const hopDeXuat = document.createElement("div");
  box.appendChild(hopDeXuat);
  function veDeXuat() {
    hopDeXuat.textContent = "";
    const ds = (CAU_HINH.de_xuat_anh_xa || {})[chonClient.value] || [];
    if (!ds.length) return;
    hopDeXuat.appendChild(nhan(UI.map_de_xuat, "ghi-chu"));
    for (const d of ds.slice(0, 8)) {
      const dong = document.createElement("div");
      dong.className = "o-va-nut";
      dong.appendChild(nhan(d.master_symbol + " \u2192 " + d.client_symbol
                            + (d.chac_chan ? "" : " " + UI.map_de_xuat_can_xem)));
      const b = nut(UI.map_de_xuat_nhan);
      b.onclick = () => {
        if (sMaster.tagName === "SELECT" || sMaster.tagName === "INPUT") {
          sMaster.value = d.master_symbol;
        }
        oClient.value = d.client_symbol;
      };
      dong.appendChild(b);
      hopDeXuat.appendChild(dong);
    }
  }
  veDeXuat();
  const them = nut(UI.map_add, "chinh");
  // Nut nay LUU, va phia server kiem symbol voi san truoc khi luu. Khong co duong nao luu mot
  // anh xa chua kiem: sai ten symbol mot ky tu chi lo ra dung luc co lenh that di qua.
  them.onclick = () => ghiCauHinh("/api/symbol_map", {
    client_id: chonClient.value,
    master_symbol: sMaster.value,
    client_symbol: oClient.value,
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

// Doi tab. Tach khoi vong gan onclick de mo duoc tab bang location.hash.
function moTab(t) {
  document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
  document.querySelectorAll(".man").forEach((x) => x.classList.add("an"));
  t.classList.add("active");
  $(t.dataset.man).classList.remove("an");
  // Ghi lai vao hash: F5 hay mot duong link se ve dung tab, thay vi ve Tong quan.
  if (location.hash.slice(1) !== t.dataset.man) location.hash = t.dataset.man;
  if (t.dataset.man === "huong-dan") taiHuongDan();
  if (t.dataset.man === "sai-lech") taiSaiLech();
  if (t.dataset.man === "nhat-ky") taiNhatKy();
  if (t.dataset.man === "cau-hinh") taiCauHinh();
}

// -- trang Huong dan --------------------------------------------------------------------------

// Mot buoc. Ba trang thai, va chung KHAC NHAU ve ban chat:
//   XONG / CON_THIEU : Bridge tu kiem duoc, khong co o tich -- tich tay mot viec chua lam xong
//                      la tu bit mat minh.
//   TU_TICH          : Bridge KHONG thay duoc (gan EA len chart, bam Ctrl+F5, mo Toolbox), nen
//                      day la cho duy nhat co o tich.
function dongBuoc(b) {
  const li = document.createElement("li");
  li.className = b.trang_thai === "CON_THIEU" ? "chan"
               : b.trang_thai === "XONG" ? "xong" : "luu-y";

  if (b.tu_kiem) {
    const the = document.createElement("span");
    the.className = "the-muc";
    the.textContent = b.trang_thai === "XONG" ? "\u2713" : "\u2715";
    li.appendChild(the);
  } else {
    const o = document.createElement("input");
    o.type = "checkbox";
    o.checked = !!b.da_tich;
    o.className = "o-tich";
    o.onchange = async () => {
      const r = await goi("/api/huong_dan/tich", {
        method: "POST", body: JSON.stringify({ ma: b.ma, tich: o.checked }) });
      if (!r.ok) { o.checked = !o.checked; alert(r.data.message || r.data.error || ""); return; }
      taiHuongDan();
    };
    if (b.da_tich) li.classList.add("xong");
    li.appendChild(o);
  }

  li.appendChild(document.createTextNode(" " + b.chu));

  // Khoi "Dang con thieu" nam NGOAI phan Chi tiet: no la ly do buoc nay dang do, va mot ly do
  // phai bam moi thay thi khong khac gi khong co. `viec_can_lam` da sinh san mot dong cho TUNG
  // doi tuong -- agent nao, Client nao -- nen chi viec in ra.
  if (b.thieu && b.thieu.length) {
    const kh = document.createElement("div");
    kh.className = "buoc-thieu";
    kh.appendChild(nhan(UI.hd_nhan_thieu + ":", "nhan-nho"));
    const ds = document.createElement("ul");
    for (const t of b.thieu) {
      const d = document.createElement("li");
      d.textContent = t;
      ds.appendChild(d);
    }
    kh.appendChild(ds);
    li.appendChild(kh);
  }

  li.appendChild(chiTietBuoc(b));
  return li;
}

// Bam de chon het: nguoi ta dang o RDP, va boi den mot dong lenh dai bang chuot qua RDP la thu de
// bo giua.
function khoiLenh(lenh) {
  const ma = document.createElement("pre");
  ma.className = "lenh";
  ma.textContent = lenh;
  ma.onclick = () => {
    const r = document.createRange();
    r.selectNodeContents(ma);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(r);
  };
  return ma;
}

// Phan chi tiet cua mot buoc: lam o dau, tung viec con theo thu tu, cach tu kiem, cai bay, va
// duong dong lenh. Dong san -- danh sach mo het ra thi dai qua man hinh va thanh mot buc tuong chu.
function chiTietBuoc(b) {
  const hop = document.createElement("details");
  hop.className = "chi-tiet-buoc";
  const dau = document.createElement("summary");
  dau.textContent = UI.hd_chi_tiet;
  hop.appendChild(dau);

  const noi = { DASHBOARD: UI.hd_noi_dashboard, MT5: UI.hd_noi_mt5,
                POWERSHELL: UI.hd_noi_powershell }[b.noi];
  if (noi) hop.appendChild(nhan(UI.hd_nhan_noi + ": " + noi, "buoc-noi"));

  if (b.viec && b.viec.length) {
    hop.appendChild(nhan(UI.hd_nhan_viec + ":", "nhan-nho"));
    const ds = document.createElement("ol");
    ds.className = "ds-viec";
    for (const v of b.viec) {
      const d = document.createElement("li");
      d.textContent = v;
      ds.appendChild(d);
    }
    hop.appendChild(ds);
  }

  if (b.kiem) hop.appendChild(nhan(UI.hd_nhan_kiem + ": " + b.kiem, "buoc-kiem"));
  if (b.bay) hop.appendChild(nhan(UI.hd_nhan_bay + ": " + b.bay, "buoc-bay"));
  if (b.lenh) {
    hop.appendChild(nhan(UI.hd_nhan_lenh + ":", "nhan-nho"));
    hop.appendChild(khoiLenh(b.lenh));
  }
  return hop;
}

function nhomHuongDan(n, moSan) {
  const hop = document.createElement("details");
  hop.className = "nhom-huong-dan";
  hop.open = moSan;
  const dau = document.createElement("summary");
  const conLai = n.buoc.filter((b) => b.trang_thai === "CON_THIEU"
                                   || (!b.tu_kiem && !b.da_tich)).length;
  dau.textContent = n.ten + (conLai ? " (" + conLai + ")" : " \u2713");
  hop.appendChild(dau);
  hop.appendChild(nhan(n.chu, "ghi-chu"));
  if (!n.buoc.length) {
    hop.appendChild(nhan(UI.hd_het_viec, "ghi-chu"));
    return hop;
  }
  const ds = document.createElement("ol");
  ds.className = "ds-buoc";
  for (const b of n.buoc) ds.appendChild(dongBuoc(b));
  hop.appendChild(ds);
  return hop;
}

async function taiHuongDan() {
  const r = await goi("/api/huong_dan");
  if (!r.ok) return;
  UI = r.data.ui || UI;
  dat("tieu-de-huong-dan", UI.hd_title);
  const el = $("noi-dung-huong-dan");
  el.textContent = "";
  if (r.data.moc_cap_nhat) {
    el.appendChild(nhan(UI.hd_moc_cap_nhat.replace("{moc}",
      new Date(r.data.moc_cap_nhat).toLocaleString("vi-VN")), "ghi-chu"));
  }
  for (const n of r.data.nhom) el.appendChild(nhomHuongDan(n, n.ma === r.data.che_do));
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
  khoiCanLam(el);
  khoiAgent(el);
  khoiClient(el);
  khoiMaster(el);
  khoiAnhXa(el);
  // Ba khoi duoi day la thu mot ban cai binh thuong KHONG BAO GIO dung toi: bay khoa ky thuat
  // deu co mac dinh an toan, config.toml do trinh cai ghi, va Dat lai la duong mot chieu. De
  // chung mo san thi trang Cau hinh dai gap doi vi nhung thu khong ai sua.
  const nangCao = document.createElement("details");
  nangCao.className = "nhom-huong-dan";
  const dau = document.createElement("summary");
  dau.textContent = UI.cfg_nang_cao;
  nangCao.appendChild(dau);
  nangCao.appendChild(nhan(UI.cfg_nang_cao_hint, "ghi-chu"));
  el.appendChild(nangCao);
  khoiHeThong(nangCao);
  khoiFileConfig(nangCao);
  khoiDatLai(nangCao);
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

  document.querySelectorAll(".tab").forEach((t) => { t.onclick = () => moTab(t); });

  // Mo tab theo #hash. Script cai dat mo san dia chi dashboard kem "#huong-dan" sau khi cai
  // xong, nen day la duong nguoi dung di vao lan dau -- khong co doan nay thi ho roi vao Tong
  // quan va phai tu tim ra tab Huong dan.
  const tabTheoHash = () => {
    const t = document.querySelector('.tab[data-man="' + location.hash.slice(1) + '"]');
    if (t && !t.classList.contains("active")) moTab(t);
  };
  tabTheoHash();
  // Doi hash tren mot tab DANG MO thi trinh duyet KHONG tai lai trang. Thieu dong nay thi khi
  // dashboard da mo san ma script cai dat mo lai cung dia chi kem "#huong-dan", trinh duyet chi
  // doi thanh dia chi roi khong lam gi -- nguoi dung nhin thay Tong quan va khong hieu huong dan
  // o dau. Bat duoc bang Playwright, khong phai bang doc code.
  window.addEventListener("hashchange", tabTheoHash);

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
