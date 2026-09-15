import { Fragment, createContext, useContext, useEffect, useRef, useState } from "react";
import ReactFlow, {
  Background, Controls, Handle, Position, ReactFlowProvider, useEdgesState, useNodesState,
} from "reactflow";
import "reactflow/dist/style.css";
import { api } from "./api";
import SettingsDrawer from "./Settings.jsx";

const STAGE_LABEL = {
  idea: "Идея", script: "Сценарий", style: "Стиль",
  storyboard: "Раскадровка", shots: "Шоты", assembly: "Сборка",
};
const BRANCH = [
  { key: "idea", n: 1, title: "Идея" },
  { key: "script", n: 2, title: "Сценарий" },
  { key: "style", n: 3, title: "Визуал-стиль" },
  { key: "storyboard", n: 4, title: "Раскадровка + шоты" },
  { key: "assembly", n: 5, title: "Сборка" },
];
const stageKey = (s) => (s === "shots" ? "storyboard" : s);

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

  useEffect(() => {
    setExpanded(new Set([stageKey(project.stage)]));
  }, [project.id]);
  useEffect(() => {
    api.getVoices().then(setVoices).catch(() => {});
    api.getCameraPresets().then(setPresets).catch(() => {});
  }, []);

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
  const stageStatus = (key) => {
    const has = {
      idea: !!project.brief_text,
      script: project.scenes.length > 0,
      style: project.concepts.length > 0,
      storyboard: shotsCount > 0,
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
    expanded, toggleExpand,
  };

  return (
    <PC.Provider value={ctx}>
      <div className="canvas-root">
        <div className="canvas-top">
          <h2 className="pname">{project.title}</h2>
          <div className="canvas-actions">
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

const nodeTypes = { stage: StageNode };

function Board({ project }) {
  const posKey = "vs_pos_" + project.id;
  const saved = (() => {
    try { return JSON.parse(localStorage.getItem(posKey)) || {}; } catch { return {}; }
  })();
  const [nodes, , onNodesChange] = useNodesState(
    BRANCH.map((st, i) => ({
      id: st.key,
      type: "stage",
      position: saved[st.key] || { x: i * 300, y: 60 },
      data: { key: st.key, n: st.n, title: st.title },
      dragHandle: ".gnode-head",
    }))
  );
  const [edges] = useEdgesState(
    BRANCH.slice(1).map((st, i) => ({ id: "e" + i, source: BRANCH[i].key, target: st.key }))
  );

  useEffect(() => {
    const pos = {};
    nodes.forEach((n) => { pos[n.id] = n.position; });
    try { localStorage.setItem(posKey, JSON.stringify(pos)); } catch { /* ignore */ }
  }, [nodes, posKey]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
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
    <div className={`gnode ${open ? "open" : ""} ${status}`}>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
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

function StageBody({ k }) {
  const c = useContext(PC);
  const { project, busy } = c;

  if (k === "idea") return <IdeaPanel />;

  if (k === "script") return (
    <>
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
        {project.scenes.map((sc) => (
          <div key={sc.id} className="sb-scene">
            {sc.shots?.length > 0 && <div className="sb-scene-title">Сцена {sc.order}</div>}
            <div className="shots">
              {(sc.shots || []).map((sh) => (
                <div key={sh.id} className={`shot ${sh.status}`}>
                  <div className="shot-media">
                    {sh.frame_url ? <img src={sh.frame_url} alt="" /> : <div className="ph">кадр не сгенерирован</div>}
                    <span className="dur">{sh.duration}с</span>
                  </div>
                  <div className="shot-body">
                    {c.editKey === "shot:" + sh.id ? (
                      <EditBox initial={sh.description} busy={busy === "edit"} onCancel={() => c.setEditKey(null)}
                        onSave={(val) => c.commitEdit(() => api.patchShot(sh.id, { description: val }))} />
                    ) : (
                      <>
                        <p className="shot-desc">{sh.description}</p>
                        <div className="shot-meta"><span>🎥 {sh.camera}</span><span>💡 {sh.lighting}</span></div>
                        <div className="row">
                          <button disabled={busy} onClick={() => c.run("frame:" + sh.id, async () => { await api.generateFrame(sh.id); return api.getProject(project.id); })}>
                            {busy === "frame:" + sh.id ? "…" : sh.frame_url ? "↻ Кадр" : "Кадр"}
                          </button>
                          <button onClick={() => c.startEdit("shot:" + sh.id)}>✎</button>
                          <button onClick={() => c.run("shot", async () => { await api.decideShot(sh.id, "approve"); return api.getProject(project.id); })}>✓</button>
                          <button onClick={() => c.run("shot", async () => { await api.decideShot(sh.id, "reject"); return api.getProject(project.id); })}>✕</button>
                          <button className={c.openShot === sh.id ? "primary" : ""}
                            onClick={() => c.setOpenShot(c.openShot === sh.id ? null : sh.id)}>⚙ Элементы</button>
                        </div>
                      </>
                    )}
                  </div>
                  {c.openShot === sh.id && <ShotEditor shot={sh} />}
                </div>
              ))}
            </div>
          </div>
        ))}
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
