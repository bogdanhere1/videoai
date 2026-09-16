import { Fragment, createContext, useContext, useEffect, useRef, useState } from "react";
import ReactFlow, {
  Background, Controls, Handle, NodeResizeControl, Position, ReactFlowProvider, useNodesState,
} from "reactflow";
import "reactflow/dist/style.css";
import { api } from "./api";
import SettingsDrawer from "./Settings.jsx";

const STAGE_LABEL = {
  idea: "Идея", script: "Сценарий", style: "Стиль",
  storyboard: "Раскадровка", shots: "Шоты", assembly: "Сборка",
};
const BRANCH = [
  { key: "script", n: 1, title: "Идея + Сценарий" },
  { key: "style", n: 2, title: "Визуал-стиль" },
  { key: "storyboard", n: 3, title: "Раскадровка (статика)" },
  { key: "shots", n: 4, title: "Шоты (анимация)" },
  { key: "assembly", n: 5, title: "Сборка" },
];
const stageKey = (s) => (s === "idea" ? "script" : s);
const DEFAULT_W = { script: 340, style: 320, storyboard: 640, shots: 640, assembly: 320 };
const refUrl = (r) => (typeof r === "string" ? r : r?.url);
const MOD_META = {
  style: { icon: "🎨", title: "Стиль", accent: "style", upload: true, gen: false,
    ph: "cinematic 3D, pixar-like, warm palette, soft rim light" },
  character: { icon: "🧍", title: "Персонаж", accent: "character", upload: false, gen: true,
    ph: "young female barista, red apron, freckles, curly auburn hair",
    hint: "тело без головы (2 ракурса) + крупный детальный портрет лица — чтобы лицо не «мылилось»" },
  location: { icon: "🏙", title: "Локация", accent: "location", upload: false, gen: true,
    ph: "cozy modern cafe interior, morning light, plants",
    hint: "общий план + другой ракурс + деталь/атмосфера (без людей)" },
  camera: { icon: "🎥", title: "Камера", accent: "camera", upload: false, gen: false,
    ph: "35mm lens, low angle, shallow depth of field, slow dolly in" },
  light: { icon: "💡", title: "Свет", accent: "light", upload: false, gen: false,
    ph: "golden hour, soft rim light, moody, high contrast" },
};

const PC = createContext(null);

export default function App() {
  const [health, setHealth] = useState(null);
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);

  const refresh = () => api.listProjects().then(setProjects).catch(() => {});
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "offline" }));
    refresh();
  }, []);

  const open = (id) => api.getProject(id).then(setProject);
  const newProject = async () => {
    const p = await api.createProject("Новый ролик");
    await refresh();
    open(p.id);
  };

  return (
    <div className="app">
      <header>
        <h1>AI Video Studio</h1>
        <span className="badge">API: {health ? health.status : "…"}</span>
      </header>
      <div className="body">
        <aside>
          <button className="primary" onClick={newProject}>+ Новый ролик</button>
          <ul className="plist">
            {projects.map((p) => (
              <li key={p.id} className={project?.id === p.id ? "sel" : ""} onClick={() => open(p.id)}>
                <div>{p.title}</div>
                <small>{STAGE_LABEL[p.stage]} · {p.status}</small>
              </li>
            ))}
          </ul>
        </aside>
        <main>
          {!project ? (
            <div className="empty">Создай или выбери ролик слева</div>
          ) : (
            <ProjectView project={project} onChange={setProject} afterChange={refresh} />
          )}
        </main>
      </div>
    </div>
  );
}

function ProjectView({ project, onChange, afterChange }) {
  const [busy, setBusy] = useState("");
  const [voices, setVoices] = useState([]);
  const [presets, setPresets] = useState([]);
  const [openShot, setOpenShot] = useState(null);
  const [editKey, setEditKey] = useState(null);
  const [expanded, setExpanded] = useState(() => new Set([stageKey(project.stage)]));
  const [showSettings, setShowSettings] = useState(false);
  const [modifiers, setModifiers] = useState([]);

  const reloadModifiers = () => api.listModifiers(project.id).then(setModifiers).catch(() => {});
  useEffect(() => {
    setExpanded(new Set([stageKey(project.stage)]));
    reloadModifiers();
  }, [project.id]);
  useEffect(() => {
    api.getVoices().then(setVoices).catch(() => {});
    api.getCameraPresets().then(setPresets).catch(() => {});
  }, []);

  const addModifierNode = async (kind) => {
    const m = await api.createModifier(project.id, kind, "storyboard");
    await reloadModifiers();
    setExpanded((prev) => new Set(prev).add(m.id));
  };

  const run = async (label, fn) => {
    setBusy(label);
    try {
      const p = await fn();
      if (p?.id) onChange(p);
      afterChange();
    } catch (e) {
      alert("Ошибка: " + e.message);
    } finally {
      setBusy("");
    }
  };

  // Правка текста: значение живёт локально в EditBox, наружу приходит только на «Сохранить».
  const startEdit = (key) => setEditKey(key);
  const commitEdit = (fn) => run("edit", async () => {
    await fn();
    setEditKey(null);
    return api.getProject(project.id);
  });

  const shotsCount = project.scenes.reduce((n, s) => n + (s.shots?.length || 0), 0);
  const anyVideo = project.scenes.some((sc) => (sc.shots || []).some((sh) => sh.video_url));
  const anyFrame = project.scenes.some((sc) => (sc.shots || []).some((sh) => sh.frame_url || sh.frame_start));
  const stageStatus = (key) => {
    const has = {
      idea: !!project.brief_text,
      script: project.scenes.length > 0,
      style: project.concepts.length > 0,
      storyboard: anyFrame || shotsCount > 0,
      shots: anyVideo,
      assembly: !!project.final_url,
    }[key];
    return has ? "done" : "empty";
  };
  const toggleExpand = (key) => setExpanded((prev) => {
    const n = new Set(prev);
    n.has(key) ? n.delete(key) : n.add(key);
    return n;
  });

  const ctx = {
    project, onChange, busy, voices, presets,
    openShot, setOpenShot, editKey, setEditKey,
    startEdit, commitEdit, run, shotsCount, stageStatus,
    expanded, toggleExpand, modifiers, reloadModifiers,
  };

  return (
    <PC.Provider value={ctx}>
      <div className="canvas-root">
        <div className="canvas-top">
          <h2 className="pname">{project.title}</h2>
          <div className="canvas-actions">
            <button onClick={() => addModifierNode("style")}>+ Стиль</button>
            <button onClick={() => addModifierNode("character")}>+ Персонаж</button>
            <button onClick={() => addModifierNode("location")}>+ Локация</button>
            <button onClick={() => addModifierNode("camera")}>+ Камера</button>
            <button onClick={() => addModifierNode("light")}>+ Свет</button>
            <span className="cost">≈ ${project.cost_usd ?? 0} · API</span>
            <button onClick={() => setShowSettings(true)}>⚙ Настройки</button>
          </div>
        </div>
        <ReactFlowProvider>
          <Board key={project.id} project={project} />
        </ReactFlowProvider>
        {showSettings && (
          <SettingsDrawer projectId={project.id} onClose={() => setShowSettings(false)} />
        )}
      </div>
    </PC.Provider>
  );
}

const nodeTypes = {
  stage: StageNode, style: ModifierNode, character: ModifierNode,
  camera: ModifierNode, light: ModifierNode, location: ModifierNode,
};

function Board({ project }) {
  const ctx = useContext(PC);
  const modifiers = ctx.modifiers;
  const posKey = "vs_pos_" + project.id;
  const saved = (() => {
    try { return JSON.parse(localStorage.getItem(posKey)) || {}; } catch { return {}; }
  })();

  const posOf = (id, def) => (saved[id] ? { x: saved[id].x, y: saved[id].y } : def);
  const widthOf = (id, def) => saved[id]?.w || def;

  const stageNode = (st, i) => ({
    id: st.key, type: "stage",
    position: posOf(st.key, { x: i * 300, y: 60 }),
    style: { width: widthOf(st.key, DEFAULT_W[st.key] || 300) },
    data: { key: st.key, n: st.n, title: st.title },
    dragHandle: ".gnode-head",
  });
  const modNode = (m) => ({
    id: m.id, type: MOD_META[m.kind] ? m.kind : "style",
    position: posOf(m.id, { x: m.pos_x || 120, y: m.pos_y || 340 }),
    style: { width: widthOf(m.id, 300) },
    data: { id: m.id },
    dragHandle: ".gnode-head",
  });

  const [nodes, setNodes, onNodesChange] = useNodesState([
    ...BRANCH.map(stageNode), ...modifiers.map(modNode),
  ]);

  const modIds = modifiers.map((m) => m.id).join(",");
  useEffect(() => {
    setNodes((cur) => {
      const byId = Object.fromEntries(cur.map((n) => [n.id, n]));
      const keep = (n) => (byId[n.id]
        ? { ...n, position: byId[n.id].position, style: { ...n.style, width: byId[n.id].style?.width || n.style?.width } }
        : n);
      return [...BRANCH.map(stageNode).map(keep), ...modifiers.map(modNode).map(keep)];
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modIds]);

  useEffect(() => {
    const layout = {};
    nodes.forEach((n) => {
      layout[n.id] = { x: n.position.x, y: n.position.y, w: n.width || n.style?.width };
    });
    try { localStorage.setItem(posKey, JSON.stringify(layout)); } catch { /* ignore */ }
  }, [nodes, posKey]);

  const stageEdges = BRANCH.slice(1).map((st, i) => ({ id: "e" + i, source: BRANCH[i].key, target: st.key }));
  const targetsFor = (m) => (m.target_stage === "both" ? ["style", "storyboard"]
    : ["style", "storyboard"].includes(m.target_stage) ? [m.target_stage] : []);
  const modEdges = modifiers.flatMap((m) => targetsFor(m).map((t) => ({
    id: "m" + m.id + t, source: m.id, target: t, animated: true,
    style: { stroke: "#a78bfa" }, data: { mid: m.id, stage: t },
  })));

  const onConnect = async ({ source, target }) => {
    const m = modifiers.find((x) => x.id === source);
    if (!m || !["style", "storyboard"].includes(target)) return;
    const cur = m.target_stage;
    const next = (cur && cur !== "none" && cur !== target) ? "both" : target;
    await api.patchModifier(m.id, { target_stage: next });
    ctx.reloadModifiers();
  };
  const onEdgesDelete = async (deleted) => {
    for (const e of deleted) {
      const d = e.data || {};
      if (!d.mid) continue;
      const m = modifiers.find((x) => x.id === d.mid);
      if (!m) continue;
      const next = m.target_stage === "both"
        ? (d.stage === "style" ? "storyboard" : "style") : "none";
      await api.patchModifier(m.id, { target_stage: next });
    }
    ctx.reloadModifiers();
  };

  return (
    <ReactFlow
      nodes={nodes}
      edges={[...stageEdges, ...modEdges]}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onConnect={onConnect}
      onEdgesDelete={onEdgesDelete}
      minZoom={0.2}
      maxZoom={1.75}
      fitView
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={22} color="#334155" />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}

function StageNode({ data }) {
  const ctx = useContext(PC);
  const status = ctx.stageStatus(data.key);
  const open = ctx.expanded.has(data.key);
  return (
    <div className={`gnode stage-${data.key} ${open ? "open" : ""} ${status}`}>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <NodeResizeControl position="right" variant="line" minWidth={200} maxWidth={1100} className="rz" />
      <div className="gnode-head" title="Перетащи за шапку">
        <span className="gnode-grip">⠿</span>
        <span className={`gnode-n ${status}`}>{status === "done" ? "✓" : data.n}</span>
        <span className="gnode-title">{data.title}</span>
        <button className="gnode-toggle nodrag" onClick={() => ctx.toggleExpand(data.key)}>
          {open ? "▾" : "▸"}
        </button>
      </div>
      {open && (
        <div className="gnode-body nodrag">
          <StageBody k={data.key} />
        </div>
      )}
    </div>
  );
}

function ModifierNode({ data }) {
  const ctx = useContext(PC);
  const m = ctx.modifiers.find((x) => x.id === data.id);
  const open = ctx.expanded.has(data.id);
  if (!m) return null;
  const meta = MOD_META[m.kind] || MOD_META.style;
  return (
    <div className={`gnode ${meta.accent} ${open ? "open" : ""} ${m.enabled ? "on" : "off"}`}>
      <Handle type="source" position={Position.Right} />
      <NodeResizeControl position="right" variant="line" minWidth={200} maxWidth={700} className="rz" />
      <div className="gnode-head" title="Перетащи за шапку">
        <span className="gnode-grip">⠿</span>
        <span className="gnode-badge">{meta.icon}</span>
        <span className="gnode-title">{meta.title}{m.enabled ? "" : " (выкл)"}</span>
        <button className="gnode-toggle nodrag" onClick={() => ctx.toggleExpand(data.id)}>
          {open ? "▾" : "▸"}
        </button>
      </div>
      {open && <div className="gnode-body nodrag"><ModifierBody m={m} meta={meta} /></div>}
    </div>
  );
}

function ModifierBody({ m, meta }) {
  const { reloadModifiers } = useContext(PC);
  const [text, setText] = useState(m.reference_text || "");
  const [target, setTarget] = useState(m.target_stage || "storyboard");
  const [busy, setBusy] = useState("");
  const fileRef = useRef(null);
  const views = (m.refs || []).filter((r) => typeof r === "object");
  const flat = (m.refs || []).filter((r) => typeof r === "string");

  const persist = () => api.patchModifier(m.id, { reference_text: text, target_stage: target });
  const save = async () => {
    setBusy("save");
    try { await persist(); await reloadModifiers(); } catch (e) { alert(e.message); } finally { setBusy(""); }
  };
  const gen = async () => {
    setBusy("gen");
    try { await persist(); await api.generateViews(m.id); await reloadModifiers(); }
    catch (e) { alert("Генерация: " + e.message); } finally { setBusy(""); }
  };
  const onFile = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    setBusy("up");
    try { await api.uploadReference(m.id, f); await reloadModifiers(); }
    catch (err) { alert(err.message); } finally { setBusy(""); e.target.value = ""; }
  };
  const toggle = async () => { await api.patchModifier(m.id, { enabled: !m.enabled }); reloadModifiers(); };
  const del = async () => {
    if (confirm(`Удалить узел «${meta.title}»?`)) { await api.deleteModifier(m.id); reloadModifiers(); }
  };

  return (
    <>
      <label className="el-label">{meta.gen ? "Описание (EN)" : "Референс (текст, EN)"}</label>
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={"напр. " + meta.ph} />
      {meta.hint && <p className="hint">Сгенерит: {meta.hint}.</p>}
      <label className="el-label">Подключить к этапу (или тяни ребро мышью)</label>
      <select value={target} onChange={(e) => setTarget(e.target.value)}>
        <option value="none">— не подключено —</option>
        <option value="style">Визуал-стиль</option>
        <option value="storyboard">Раскадровка</option>
        <option value="both">Оба</option>
      </select>
      {views.length > 0 && (
        <div className="refs labeled">
          {views.map((r, i) => (
            <figure key={i}><img src={r.url} alt="" /><figcaption>{r.label}</figcaption></figure>
          ))}
        </div>
      )}
      {flat.length > 0 && (
        <div className="refs">{flat.map((u, i) => <img key={i} src={refUrl(u)} alt="ref" />)}</div>
      )}
      <div className="row">
        {meta.gen && (
          <button className="primary" disabled={!!busy} onClick={gen}>
            {busy === "gen" ? "Генерирую виды…" : "Сгенерировать виды"}
          </button>
        )}
        {meta.upload && (
          <>
            <button disabled={!!busy} onClick={() => fileRef.current?.click()}>
              {busy === "up" ? "…" : "📎 Референс"}
            </button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={onFile} />
          </>
        )}
        <button className={meta.gen ? "" : "primary"} disabled={!!busy} onClick={save}>
          {busy === "save" ? "…" : "Сохранить"}
        </button>
      </div>
      <div className="row">
        <button onClick={toggle}>{m.enabled ? "Выключить" : "Включить"}</button>
        <button onClick={del}>🗑 Удалить</button>
      </div>
    </>
  );
}

function FrameSlot({ url, label, busy, onGen, dur }) {
  return (
    <div className="frame-slot">
      <div className="shot-media">
        {url ? <img src={url} alt={label} /> : <div className="ph">нет кадра</div>}
        {dur ? <span className="dur">{dur}с</span> : null}
        <span className="slot-label">{label}</span>
      </div>
      <button className="wfull" disabled={busy} onClick={onGen}>
        {busy ? "…" : url ? "↻ " + label : label}
      </button>
    </div>
  );
}

function SequencePlayer({ scenes }) {
  const ref = useRef(null);
  const [idx, setIdx] = useState(0);
  const urls = scenes.flatMap((sc) => (sc.shots || [])
    .filter((sh) => sh.status !== "rejected" && sh.video_url)
    .map((sh) => sh.video_url));
  if (urls.length === 0) {
    return <p className="hint">Видео шотов ещё нет — плеер появится, когда сгенерируешь
      ролики шотов (ждёт баланс Higgsfield).</p>;
  }
  const playFrom = (n) => {
    setIdx(n);
    const v = ref.current; if (!v) return;
    v.src = urls[n]; v.currentTime = 0; v.play().catch(() => {});
  };
  const onEnded = () => { if (idx + 1 < urls.length) playFrom(idx + 1); };
  return (
    <div className="seq-player">
      <video ref={ref} src={urls[idx]} controls onEnded={onEnded} />
      <div className="row">
        <button className="primary" onClick={() => playFrom(0)}>▶ Играть всё</button>
        <span className="muted">шот {idx + 1} / {urls.length}</span>
      </div>
    </div>
  );
}

function StageBody({ k }) {
  const c = useContext(PC);
  const { project, busy } = c;

  if (k === "script") return (
    <>
      <IdeaPanel />
      <div className="stage-sep" />
      {project.logline && <p className="logline">«{project.logline}»</p>}
      <button className="primary" disabled={!project.brief_text || busy}
        onClick={() => c.run("script", () => api.generateScript(project.id))}>
        {busy === "script" ? "Генерирую…" : project.scenes.length ? "Перегенерировать" : "Сгенерировать сценарий"}
      </button>
      {project.scenes.map((s) => (
        <div key={s.id} className={`scene ${s.status}`}>
          <div className="scene-head"><b>Сцена {s.order}</b><span className={`tag ${s.status}`}>{s.status}</span></div>
          {c.editKey === "scene:" + s.id ? (
            <EditBox initial={s.script_text} busy={busy === "edit"} onCancel={() => c.setEditKey(null)}
              onSave={(val) => c.commitEdit(() => api.editScene(s.id, val))} />
          ) : (
            <>
              <pre>{s.script_text}</pre>
              <div className="row">
                <button onClick={() => c.startEdit("scene:" + s.id)}>✎ Править</button>
                <button onClick={() => c.run("scene", async () => { await api.decideScene(s.id, "approve"); return api.getProject(project.id); })}>✓ Ок</button>
                <button onClick={() => c.run("scene", async () => { await api.decideScene(s.id, "reject"); return api.getProject(project.id); })}>✕ Переделать</button>
              </div>
            </>
          )}
        </div>
      ))}
      {project.scenes.length > 0 && <RevisePanel />}
    </>
  );

  if (k === "style") return (
    project.concepts.length === 0 ? (
      <button className="primary" disabled={!project.scenes.length || busy}
        onClick={() => c.run("visuals", () => api.extractVisuals(project.id))}>
        {busy === "visuals" ? "Извлекаю…" : "Извлечь визуалы из сценария"}
      </button>
    ) : (
      <>
        <button disabled={busy} onClick={() => c.run("visuals", () => api.extractVisuals(project.id))}>
          {busy === "visuals" ? "…" : "↻ Пересобрать визуалы"}
        </button>
        <div className="concepts">
          {project.concepts.map((cc) => (
            <div key={cc.id} className={`concept ${cc.approved ? "approved" : ""}`}>
              <div className="concept-media">
                {cc.url ? <img src={cc.url} alt={cc.name} /> : <div className="ph">нет картинки</div>}
                <span className={`kind ${cc.kind}`}>{cc.kind === "character" ? "персонаж" : "окружение"}</span>
              </div>
              <div className="concept-body">
                <b>{cc.name}</b>
                {c.editKey === "concept:" + cc.id ? (
                  <EditBox initial={cc.prompt} busy={busy === "edit"} onCancel={() => c.setEditKey(null)}
                    onSave={(val) => c.commitEdit(() => api.editConcept(cc.id, val))} />
                ) : (
                  <>
                    <p className="cprompt">{cc.prompt}</p>
                    <div className="row">
                      <button disabled={busy} onClick={() => c.run("concept:" + cc.id, async () => { await api.generateConcept(cc.id); return api.getProject(project.id); })}>
                        {busy === "concept:" + cc.id ? "Генерирую…" : cc.url ? "↻ Перегенерировать" : "Сгенерировать"}
                      </button>
                      <button onClick={() => c.startEdit("concept:" + cc.id)}>✎</button>
                      {cc.url && (
                        <>
                          <button onClick={() => c.run("concept", async () => { await api.decideAsset(cc.id, "approve"); return api.getProject(project.id); })}>✓</button>
                          <button onClick={() => c.run("concept", async () => { await api.decideAsset(cc.id, "reject"); return api.getProject(project.id); })}>✕</button>
                        </>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </>
    )
  );

  if (k === "storyboard") return (
    c.shotsCount === 0 ? (
      <button className="primary" disabled={!project.scenes.length || busy}
        onClick={() => c.run("storyboard", () => api.generateStoryboard(project.id))}>
        {busy === "storyboard" ? "Раскадровываю…" : "Сделать раскадровку"}
      </button>
    ) : (
      <>
        <button disabled={busy} onClick={() => c.run("storyboard", () => api.generateStoryboard(project.id))}>
          {busy === "storyboard" ? "…" : "↻ Пересобрать раскадровку"}
        </button>
        <p className="hint">Только статичные кадры. На шот: один кадр или старт+финал
          (общий сид → консистентная сцена, меняется поза/действие).</p>
        <div className="shots-strip">
          {project.scenes.flatMap((sc) => (sc.shots || []).map((sh, i) => {
            const mode = sh.frame_mode || "single";
            const setMode = (mm) => c.run("shot", async () => { await api.patchShot(sh.id, { frame_mode: mm }); return api.getProject(project.id); });
            const genFrame = (v) => c.run("frame:" + sh.id + v, async () => { await api.generateFrame(sh.id, v); return api.getProject(project.id); });
            return (
              <div key={sh.id} className={`shot ${sh.status}`}>
                {i === 0 && <div className="strip-scene">Сцена {sc.order}</div>}
                <div className="seg-row nodrag">
                  <button className={mode === "single" ? "seg on" : "seg"} onClick={() => setMode("single")}>1 кадр</button>
                  <button className={mode === "startend" ? "seg on" : "seg"} onClick={() => setMode("startend")}>Старт+Финал</button>
                </div>
                {mode === "single" ? (
                  <FrameSlot url={sh.frame_single || sh.frame_url} label="Кадр" dur={sh.duration}
                    busy={busy === "frame:" + sh.id + "single"} onGen={() => genFrame("single")} />
                ) : (
                  <div className="frame-pair">
                    <FrameSlot url={sh.frame_start} label="Старт"
                      busy={busy === "frame:" + sh.id + "start"} onGen={() => genFrame("start")} />
                    <FrameSlot url={sh.frame_end} label="Финал"
                      busy={busy === "frame:" + sh.id + "end"} onGen={() => genFrame("end")} />
                  </div>
                )}
                <div className="shot-body">
                  {c.editKey === "shot:" + sh.id ? (
                    <EditBox initial={sh.description} busy={busy === "edit"} onCancel={() => c.setEditKey(null)}
                      onSave={(val) => c.commitEdit(() => api.patchShot(sh.id, { description: val }))} />
                  ) : (
                    <>
                      <p className="shot-desc">{sh.description}</p>
                      <div className="shot-meta"><span>🎥 {sh.camera}</span><span>💡 {sh.lighting}</span></div>
                      <div className="row">
                        <button onClick={() => c.startEdit("shot:" + sh.id)}>✎ Править</button>
                        <button onClick={() => c.run("shot", async () => { await api.decideShot(sh.id, "approve"); return api.getProject(project.id); })}>✓</button>
                        <button onClick={() => c.run("shot", async () => { await api.decideShot(sh.id, "reject"); return api.getProject(project.id); })}>✕</button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            );
          }))}
        </div>
      </>
    )
  );

  if (k === "shots") return (
    c.shotsCount === 0 ? (
      <p className="hint">Сначала сделай раскадровку — здесь оживим утверждённые кадры в видео.</p>
    ) : (
      <>
        <SequencePlayer scenes={project.scenes} />
        <div className="shots-strip">
          {project.scenes.flatMap((sc) => (sc.shots || []).map((sh, i) => (
            <div key={sh.id} className={`shot ${sh.status}`}>
              {i === 0 && <div className="strip-scene">Сцена {sc.order}</div>}
              <div className="shot-media">
                {sh.video_url
                  ? <video src={sh.video_url} controls />
                  : (sh.frame_url ? <img src={sh.frame_url} alt="" /> : <div className="ph">нет кадра</div>)}
                <span className="dur">{sh.duration}с</span>
              </div>
              <div className="shot-body">
                <p className="shot-desc">{sh.description}</p>
                <div className="row">
                  <button className={c.openShot === sh.id ? "primary" : ""}
                    onClick={() => c.setOpenShot(c.openShot === sh.id ? null : sh.id)}>⚙ Элементы</button>
                </div>
              </div>
              {c.openShot === sh.id && <ShotEditor shot={sh} />}
            </div>
          )))}
        </div>
      </>
    )
  );

  if (k === "assembly") return (
    <>
      <button className="primary" disabled={c.shotsCount === 0 || busy}
        onClick={() => c.run("assemble", async () => { await api.assembleProject(project.id); return api.getProject(project.id); })}>
        {busy === "assemble" ? "Собираю…" : project.final_url ? "↻ Пересобрать ролик" : "Собрать ролик"}
      </button>
      <p className="hint" style={{ marginTop: 8 }}>
        Склейка шотов + сведение звука через ffmpeg. Видео шотов — Higgsfield (ждёт баланс);
        без видео шот берётся как статичный кадр.
      </p>
      {project.final_url && (
        <video controls src={project.final_url} style={{ width: "100%", marginTop: 12, borderRadius: 10 }} />
      )}
    </>
  );

  return null;
}

function EditBox({ initial, busy, onSave, onCancel }) {
  const [val, setVal] = useState(initial || "");
  return (
    <>
      <textarea className="scene-edit" rows={5} value={val} autoFocus
        onChange={(e) => setVal(e.target.value)} />
      <div className="row">
        <button className="primary" disabled={busy} onClick={() => onSave(val)}>
          {busy ? "…" : "Сохранить"}
        </button>
        <button onClick={onCancel}>Отмена</button>
      </div>
    </>
  );
}

function IdeaPanel() {
  const { project, run } = useContext(PC);
  const [text, setText] = useState(project.brief_text || "");
  const [rec, setRec] = useState(false);
  const [stt, setStt] = useState(false);
  const mediaRef = useRef(null);
  useEffect(() => { setText(project.brief_text || ""); }, [project.id]);

  const toggleRec = async () => {
    if (rec) { mediaRef.current?.stop(); return; }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mr = new MediaRecorder(stream);
    const chunks = [];
    mr.ondataavailable = (e) => chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setStt(true);
      try {
        const { text: t } = await api.transcribe(new Blob(chunks, { type: "audio/webm" }));
        setText((p) => (p ? p + " " : "") + t);
      } catch (e) { alert("STT: " + e.message); } finally { setStt(false); }
    };
    mediaRef.current = mr;
    mr.start(); setRec(true);
    mr.addEventListener("stop", () => setRec(false));
  };

  return (
    <>
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Опиши идею ролика — текстом или голосом…" />
      <div className="row">
        <button onClick={toggleRec} className={rec ? "rec" : ""}>{rec ? "⏹ Стоп" : "🎤 Голос"}</button>
        <button className="primary" disabled={!text.trim()}
          onClick={() => run("idea", () => api.setIdea(project.id, text))}>
          Сохранить идею
        </button>
        {stt && <span className="muted">распознаю…</span>}
      </div>
    </>
  );
}

function RevisePanel() {
  const { project, run } = useContext(PC);
  const [fb, setFb] = useState("");
  return (
    <div className="revise">
      <textarea rows={2} value={fb} onChange={(e) => setFb(e.target.value)}
        placeholder="Правки ко всему сценарию…" />
      <button disabled={!fb.trim()}
        onClick={() => run("script", async () => { const p = await api.reviseScript(project.id, fb); setFb(""); return p; })}>
        Внести правки
      </button>
    </div>
  );
}

function ShotEditor({ shot }) {
  const { voices, presets, project, onChange } = useContext(PC);
  const projectId = project.id;
  const [f, setF] = useState({
    camera_preset: shot.camera_preset || "General",
    motion_strength: shot.motion_strength ?? 0.6,
    lighting: shot.lighting || "",
    voice_text: shot.voice_text || "",
    voice_id: shot.voice_id || "",
    music_prompt: shot.music_prompt || "",
    sfx_prompt: shot.sfx_prompt || "",
  });
  const [busy, setBusy] = useState("");
  const upd = (k, v) => setF((p) => ({ ...p, [k]: v }));

  const run = async (element) => {
    setBusy(element);
    try {
      await api.patchShot(shot.id, f);
      await api.genShotElement(shot.id, element);
      onChange(await api.getProject(projectId));
    } catch (e) { alert(element + ": " + e.message); } finally { setBusy(""); }
  };
  const save = async () => {
    setBusy("save");
    try {
      await api.patchShot(shot.id, f);
      onChange(await api.getProject(projectId));
    } catch (e) { alert(e.message); } finally { setBusy(""); }
  };
  const B = (el, label) => (
    <button disabled={!!busy} onClick={() => run(el)}>{busy === el ? "…" : label}</button>
  );

  return (
    <div className="editor">
      <div className="el-grid">
        <div className="el">
          <label>🎥 Камера</label>
          <select value={f.camera_preset} onChange={(e) => upd("camera_preset", e.target.value)}>
            {(presets.length ? presets : [f.camera_preset]).map((p) => <option key={p}>{p}</option>)}
          </select>
          <label>Сила движения: {f.motion_strength}</label>
          <input type="range" min="0" max="1" step="0.1" value={f.motion_strength}
            onChange={(e) => upd("motion_strength", parseFloat(e.target.value))} />
          <label>💡 Свет</label>
          <input value={f.lighting} onChange={(e) => upd("lighting", e.target.value)}
            placeholder="напр. golden hour, soft backlight" />
        </div>
        <div className="el">
          <label>🗣 Голос</label>
          <textarea rows={2} value={f.voice_text} onChange={(e) => upd("voice_text", e.target.value)}
            placeholder="Реплика для озвучки…" />
          <select value={f.voice_id} onChange={(e) => upd("voice_id", e.target.value)}>
            <option value="">— голос по умолчанию —</option>
            {voices.map((v) => <option key={v.voice_id} value={v.voice_id}>{v.name}</option>)}
          </select>
          <div className="row">{B("voice", shot.voice_url ? "↻ Озвучить" : "Озвучить")}</div>
          {shot.voice_url && <audio controls src={shot.voice_url} />}
        </div>
        <div className="el">
          <label>🎵 Музыка</label>
          <input value={f.music_prompt} onChange={(e) => upd("music_prompt", e.target.value)}
            placeholder="напр. calm lo-fi piano" />
          <div className="row">{B("music", shot.music_url ? "↻ Музыка" : "Музыка")}</div>
          {shot.music_url && <audio controls src={shot.music_url} />}
          <label>🔊 SFX</label>
          <input value={f.sfx_prompt} onChange={(e) => upd("sfx_prompt", e.target.value)}
            placeholder="напр. coffee machine steam" />
          <div className="row">{B("sfx", shot.sfx_url ? "↻ SFX" : "SFX")}</div>
          {shot.sfx_url && <audio controls src={shot.sfx_url} />}
        </div>
        <div className="el">
          <label>🎬 Видео / Липсинк</label>
          <div className="row">
            {B("video", shot.video_url ? "↻ Видео (DoP)" : "Видео (DoP)")}
            {B("lipsync", "Липсинк")}
          </div>
          {shot.video_url && <video controls src={shot.video_url} />}
          <p className="hint">Видео/липсинк — Higgsfield, ждут баланс. Музыка — тариф ElevenLabs.</p>
        </div>
      </div>
      <button className="primary" disabled={!!busy} onClick={save}>
        {busy === "save" ? "…" : "💾 Сохранить параметры"}
      </button>
    </div>
  );
}
