const $ = (id) => document.getElementById(id);

const PRESET_HINTS = {
  auto: "手机直出：抬阴影、咬高光、轻度颗粒。手持轻微。",
  iphone: "计算摄影：略暖、防抖更稳、对焦点会慢慢喘。",
  ugc: "转发：前 3 秒约 2% 手持然后稳住，1080p、颗粒、再压码。",
  night: "夜景：偏冷、暗部颗粒、曝光会慢慢游。",
  compress: "压片：两次编码，接近转发压缩。",
  cctv: "监控：锁死机位、重颗粒、低码、快门拖影。",
};

const PRESET_DEFAULTS = {
  auto: { shutter: 0.22, handheld: 0.34 },
  iphone: { shutter: 0.16, handheld: 0.20 },
  ugc: { shutter: 0.36, handheld: 0.72 },
  night: { shutter: 0.28, handheld: 0.40 },
  compress: { shutter: 0.20, handheld: 0.28 },
  cctv: { shutter: 0.48, handheld: 0.0 },
};

const LIGHT_HINTS = {
  auto: "按画面判断：窗边走窗光，过亮走正午，转发走混合光。",
  window: "窗光：冷高光、暖阴影，咬掉窗外，脸稍抬。",
  sun: "正午：阴影更深，高光咬死，略过曝。",
  over: "过曝：手机测光偏亮，高光更容易烧。",
  mix: "混合光：阴影偏暖、高光偏冷，破平光。",
  dim: "暗场：少抬阴影，压黑位。",
};

const state = {
  samples: [],
  current: null,
  mode: "still",
  preset: "auto",
  light: "auto",
  exposure: 0.5,
  shadows: 0.5,
  highlights: 0.5,
  shutter: 0.22,
  handheld: 0.34,
  split: 50,
  file: null,
  poll: null,
  playing: false,
  currentSampleId: null,
};

function setSplit(pct) {
  state.split = Math.min(96, Math.max(4, pct));
  const fx = $("layer-fx");
  const h = $("handle");
  fx.style.clipPath = `inset(0 0 0 ${state.split}%)`;
  h.style.left = `${state.split}%`;
  h.setAttribute("aria-valuenow", String(Math.round(state.split)));
}

function bindSlider() {
  const stage = $("stage");
  let drag = false;
  const at = (ev) => {
    const r = stage.getBoundingClientRect();
    setSplit(((ev.clientX - r.left) / r.width) * 100);
  };
  stage.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest(".empty, .stage-bar, .tag, button, a")) return;
    drag = true;
    stage.setPointerCapture(ev.pointerId);
    at(ev);
  });
  stage.addEventListener("pointermove", (ev) => { if (drag) at(ev); });
  stage.addEventListener("pointerup", () => { drag = false; });
  stage.addEventListener("pointercancel", () => { drag = false; });
}

function mediaEl(url, kind, isVideo, poster) {
  if (isVideo) {
    const v = document.createElement("video");
    v.muted = true;
    v.defaultMuted = true;
    v.loop = true;
    v.playsInline = true;
    v.setAttribute("playsinline", "");
    v.setAttribute("muted", "");
    v.preload = "auto";
    v.controls = false;
    v.dataset.kind = kind;
    if (poster) v.poster = poster;
    v.src = url;
    v.addEventListener("error", () => setStatus("视频加载失败", true));
    return v;
  }
  const img = document.createElement("img");
  img.src = url;
  img.alt = kind;
  return img;
}

function syncVideos(play) {
  const a = $("layer-orig").querySelector("video");
  const b = $("layer-fx").querySelector("video");
  if (!a || !b) return;
  if (play) {
    const t = Math.min(a.currentTime, b.currentTime) || 0;
    a.currentTime = t;
    b.currentTime = t;
    a.play();
    b.play();
    state.playing = true;
    $("play").textContent = "暂停";
  } else {
    a.pause();
    b.pause();
    state.playing = false;
    $("play").textContent = "播放";
  }
}

function showItem(item, { video = false } = {}) {
  state.current = item;
  $("empty").classList.add("hide");
  const ar = (item.probe && item.probe.width && item.probe.height)
    ? `${item.probe.width} / ${item.probe.height}`
    : "2 / 3";
  $("stage").style.setProperty("--ar", ar);
  $("layer-orig").replaceChildren(mediaEl(video ? item.orig_vid : item.orig_img, "orig", video, item.orig_img));
  $("layer-fx").replaceChildren(mediaEl(video ? item.fx_vid : item.fx_img, "fx", video, item.fx_img));
  setSplit(state.split);
  $("now-title").textContent = item.title || "";
  const dlUrl = item.fx_vid || item.fx_img;
  $("dl").hidden = !dlUrl;
  $("dl").href = dlUrl || "#";
  const ext = item.fx_vid ? "mp4" : "jpg";
  $("dl").download = `${(item.title || "lensfx").replace(/[\\/:*?"<>|]/g, "_")}.${ext}`;
  $("play").hidden = !video;
  $("btn-video").disabled = !item.fx_vid;
  if (video) {
    const a = $("layer-orig").querySelector("video");
    const b = $("layer-fx").querySelector("video");
    const onTime = () => {
      if (!a || !b || a.paused) return;
      if (Math.abs(a.currentTime - b.currentTime) > 0.12) b.currentTime = a.currentTime;
    };
    a.addEventListener("timeupdate", onTime);
    const start = () => syncVideos(true);
    const ready = () => a.readyState >= 2 && b.readyState >= 2;
    if (ready()) start();
    else {
      const kick = () => { if (ready()) start(); };
      a.addEventListener("canplay", kick, { once: true });
      b.addEventListener("canplay", kick, { once: true });
    }
  }
  renderMeta(item);
  document.querySelectorAll(".shot").forEach((el) => {
    el.classList.toggle("on", String(el.dataset.id) === String(item.id || ""));
  });
}

function renderMeta(item) {
  const p = item.params || {};
  const scene = item.scene || p.scene || [];
  $("chips").replaceChildren(
    ...scene.map((s) => {
      const el = document.createElement("span");
      el.className = "chip" + (s === "closeup" || s === "cgi-sharp" ? " hot" : "");
      el.textContent = s;
      return el;
    })
  );
  const rows = [
    ["光线", p.light_eff || p.light],
    ["曝光", p.exposure],
    ["阴影", p.shadows],
    ["高光", p.highlights],
    ["抬阴影", p.lift],
    ["咬高光", p.hi_keep],
    ["色温", p.wb_mix ? `${p.wb_temp}K` : "中性"],
    ["DCT压", p.spp_qp],
    ["运动模糊", p.shutter],
    ["手持", p.handheld],
    ["抖动 px", p.shake],
    ["颗粒", p.grain],
    ["输出边", p.max_edge],
    ["特写", p.closeup ? "是" : "否"],
  ];
  const dl = $("meta");
  dl.replaceChildren();
  for (const [k, v] of rows) {
    if (v === undefined || v === null) continue;
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = String(v);
    dl.append(dt, dd);
  }
}

function renderFilm(samples) {
  const nav = $("film");
  nav.replaceChildren();
  for (const s of samples) {
    if (!s.orig_img) continue;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "shot";
    b.dataset.id = s.id;
    b.title = s.title;
    b.innerHTML = `<img src="${s.orig_img}" alt=""><span>${s.title}</span>`;
    b.addEventListener("click", () => {
      state.mode = $("btn-video").classList.contains("on") ? "video" : "still";
      showItem(s, { video: state.mode === "video" });
      $("drop-name").textContent = `示例 · ${s.title}`;
      state.file = null;
      state.currentSampleId = s.id;
    });
    nav.append(b);
  }
}

function setMode(mode) {
  if (mode === "video" && state.current && !state.current.fx_vid) return;
  state.mode = mode;
  $("btn-still").classList.toggle("on", mode === "still");
  $("btn-video").classList.toggle("on", mode === "video");
  if (state.current) showItem(state.current, { video: mode === "video" });
}

function setStatus(text, err = false) {
  const el = $("status");
  el.textContent = text || "";
  el.classList.toggle("err", err);
}

function setProgress(pct, visible) {
  const wrap = $("progress");
  const bar = $("progress-bar");
  if (visible === false) {
    wrap.hidden = true;
    bar.style.width = "0%";
    return;
  }
  wrap.hidden = false;
  bar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
}

async function processNow() {
  const go = $("go");
  go.disabled = true;
  setStatus("提交中…");
  setProgress(8);
  const strength = Number($("strength").value);
  const shutter = Number($("shutter").value);
  const handheld = Number($("handheld").value);
  const exposure = Number($("exposure").value);
  const shadows = Number($("shadows").value);
  const highlights = Number($("highlights").value);
  let res;
  try {
    if (state.file) {
      const fd = new FormData();
      fd.append("file", state.file);
      fd.append("preset", state.preset);
      fd.append("strength", String(strength));
      fd.append("shutter", String(shutter));
      fd.append("handheld", String(handheld));
      fd.append("light", state.light);
      fd.append("exposure", String(exposure));
      fd.append("shadows", String(shadows));
      fd.append("highlights", String(highlights));
      res = await fetch("/api/process", { method: "POST", body: fd });
    } else if (state.currentSampleId) {
      res = await fetch("/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sample_id: state.currentSampleId,
          preset: state.preset,
          strength,
          shutter,
          handheld,
          light: state.light,
          exposure,
          shadows,
          highlights,
        }),
      });
    } else {
      setStatus("先选一条示例，或上传图片/视频", true);
      setProgress(0, false);
      go.disabled = false;
      return;
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "提交失败");
    pollJob(data.id);
  } catch (e) {
    setStatus(String(e.message || e), true);
    setProgress(0, false);
    go.disabled = false;
  }
}

function pollJob(id) {
  if (state.poll) clearInterval(state.poll);
  const tick = async () => {
    try {
      const res = await fetch(`/api/job/${id}`);
      const j = await res.json();
      if (j.status === "running" || j.status === "queued") {
        setStatus(j.step || "处理中…");
        setProgress(j.progress || 20);
        return;
      }
      clearInterval(state.poll);
      state.poll = null;
      $("go").disabled = false;
      if (j.status === "error") {
        setStatus(j.error || "失败", true);
        setProgress(0, false);
        return;
      }
      setStatus("完成");
      setProgress(100);
      setTimeout(() => setProgress(0, false), 900);
      const item = {
        id: "job-" + id,
        title: (j.result && j.result.title) || "上传",
        ...j.result,
      };
      state.currentSampleId = null;
      const asVideo = Boolean(item.fx_vid);
      showItem(item, { video: asVideo });
      $("btn-still").classList.toggle("on", !asVideo);
      $("btn-video").classList.toggle("on", asVideo);
      state.mode = asVideo ? "video" : "still";
    } catch (e) {
      clearInterval(state.poll);
      state.poll = null;
      $("go").disabled = false;
      setProgress(0, false);
      setStatus(String(e.message || e), true);
    }
  };
  tick();
  state.poll = setInterval(tick, 800);
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.toggle("on", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      $("tab-process").hidden = tab.dataset.tab !== "process";
      $("tab-settings").hidden = tab.dataset.tab !== "settings";
    });
  });
}

function bindSidebar() {
  $("sidebar-hide").addEventListener("click", () => {
    document.body.classList.add("sidebar-collapsed");
    $("sidebar-show").hidden = false;
  });
  $("sidebar-show").addEventListener("click", () => {
    document.body.classList.remove("sidebar-collapsed");
    $("sidebar-show").hidden = true;
  });
}

function bindControls() {
  $("btn-still").addEventListener("click", () => setMode("still"));
  $("btn-video").addEventListener("click", () => setMode("video"));
  $("play").addEventListener("click", () => syncVideos(!state.playing));
  const applyPreset = (name) => {
    state.preset = name;
    const d = PRESET_DEFAULTS[name] || PRESET_DEFAULTS.auto;
    state.shutter = d.shutter;
    state.handheld = d.handheld;
    $("shutter").value = String(d.shutter);
    $("shutter-val").textContent = d.shutter.toFixed(2);
    $("handheld").value = String(d.handheld);
    $("handheld-val").textContent = d.handheld.toFixed(2);
    $("preset-hint").textContent = PRESET_HINTS[name] || "";
    document.querySelectorAll("#modes .mode").forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.preset === name);
    });
  };
  document.querySelectorAll("#modes .mode").forEach((btn) => {
    btn.addEventListener("click", () => applyPreset(btn.dataset.preset));
  });
  const applyLight = (name) => {
    state.light = name;
    state.exposure = 0.5;
    state.shadows = 0.5;
    state.highlights = 0.5;
    $("exposure").value = "0.5";
    $("exposure-val").textContent = "0.50";
    $("shadows").value = "0.5";
    $("shadows-val").textContent = "0.50";
    $("highlights").value = "0.5";
    $("highlights-val").textContent = "0.50";
    $("light-hint").textContent = LIGHT_HINTS[name] || "";
    document.querySelectorAll("#lights .mode").forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.light === name);
    });
  };
  document.querySelectorAll("#lights .mode").forEach((btn) => {
    btn.addEventListener("click", () => applyLight(btn.dataset.light));
  });
  const strength = $("strength");
  strength.addEventListener("input", () => {
    $("strength-val").textContent = Number(strength.value).toFixed(2);
  });
  const shutter = $("shutter");
  shutter.addEventListener("input", () => {
    state.shutter = Number(shutter.value);
    $("shutter-val").textContent = state.shutter.toFixed(2);
  });
  const handheld = $("handheld");
  handheld.addEventListener("input", () => {
    state.handheld = Number(handheld.value);
    $("handheld-val").textContent = state.handheld.toFixed(2);
  });
  for (const id of ["exposure", "shadows", "highlights"]) {
    $(id).addEventListener("input", () => {
      state[id] = Number($(id).value);
      $(`${id}-val`).textContent = state[id].toFixed(2);
    });
  }
  $("go").addEventListener("click", processNow);

  const drop = $("drop");
  const file = $("file");
  const take = (f) => {
    if (!f) return;
    state.file = f;
    state.currentSampleId = null;
    $("drop-name").textContent = f.name;
    setStatus(`已选 ${f.name}，点开始处理`);
  };
  file.addEventListener("change", () => take(file.files[0]));
  drop.addEventListener("dragover", (ev) => { ev.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (ev) => {
    ev.preventDefault();
    drop.classList.remove("over");
    take(ev.dataTransfer.files[0]);
  });
}

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    const h = await res.json();
    if (h.version) $("app-version").textContent = h.version;
    $("eng-ok").textContent = h.ok ? "就绪" : "异常";
    $("eng-ff").textContent = h.ffmpeg || "—";
    $("eng-jobs").textContent = h.jobs || "—";
  } catch {
    $("eng-ok").textContent = "无法连接引擎";
  }
}

async function main() {
  bindSlider();
  bindControls();
  bindTabs();
  bindSidebar();
  setSplit(50);
  loadHealth();
  const res = await fetch("/api/samples");
  const data = await res.json();
  state.samples = data.samples || [];
  renderFilm(state.samples);
  if (state.samples[0] && state.samples[0].orig_img) {
    state.currentSampleId = state.samples[0].id;
    showItem(state.samples[0], { video: false });
    $("drop-name").textContent = `示例 · ${state.samples[0].title}`;
    if (new URLSearchParams(location.search).get("video") === "1") setMode("video");
  }
}

main().catch((e) => setStatus(String(e), true));
