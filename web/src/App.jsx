import { Fragment, useEffect, useRef, useState } from "react";
import { api } from "./api";

const STAGE_LABEL = {
  idea: "Идея", script: "Сценарий", style: "Стиль",
  storyboard: "Раскадровка", shots: "Шоты", assembly: "Сборка",
};
// Ветка-пайплайн (аккордеон): 5 узлов, «шоты» живут внутри раскадровки.
const BRANCH = [
  { key: "idea", n: 1, title: "Идея" },
  { key: "script", n: 2, title: "Сценарий" },
  { key: "style", n: 3, title: "Визуал-стиль" },
  { key: "storyboard", n: 4, title: "Раскадровка + шоты" },
  { key: "assembly", n: 5, title: "Сборка" },
];
const stageKey = (s) => (s === "shots" ? "storyboard" : s);

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
            <Project project={project} onChange={setProject} afterChange={refresh} />
          )}
        </main>
      </div>
    </div>
  );
}

function Project({ project, onChange, afterChange }) {
  const [idea, setIdea] = useState(project.brief_text || "");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState("");
  const [rec, setRec] = useState(false);
  const [voices, setVoices] = useState([]);
  const [presets, setPresets] = useState([]);
  const [openShot, setOpenShot] = useState(null);
  const [editKey, setEditKey] = useState(null);
  const [editText, setEditText] = useState("");
  const [openStage, setOpenStage] = useState(() => stageKey(project.stage));
  const mediaRef = useRef(null);

  useEffect(() => {
    setIdea(project.brief_text || "");
    setOpenStage(stageKey(project.stage));
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

  const saveIdea = () => run("idea", () => api.setIdea(project.id, idea));
  const genScript = () => run("script", () => api.generateScript(project.id));
  const revise = () => run("script", async () => {
    const p = await api.reviseScript(project.id, feedback);
    setFeedback("");
    return p;
  });
  const decide = (sceneId, d) => run("scene", async () => {
    await api.decideScene(sceneId, d);
    return api.getProject(project.id);
  });
  const startEdit = (key, text) => { setEditKey(key); setEditText(text); };
  const saveEdit = (fn) => run("edit", async () => {
    await fn(editText);
    setEditKey(null);
    return api.getProject(project.id);
  });
  const editBox = (fn) => (
    <>
      <textarea className="scene-edit" rows={5} value={editText}
        onChange={(e) => setEditText(e.target.value)} autoFocus />
      <div className="row">
        <button className="primary" disabled={busy} onClick={() => saveEdit(fn)}>
          {busy === "edit" ? "…" : "Сохранить"}
        </button>
        <button onClick={() => setEditKey(null)}>Отмена</button>
      </div>
    </>
  );
  const extractVisuals = () => run("visuals", () => api.extractVisuals(project.id));
  const genConcept = (assetId) => run("concept:" + assetId, async () => {
    await api.generateConcept(assetId);
    return api.getProject(project.id);
  });
  const decideConcept = (assetId, d) => run("concept", async () => {
    await api.decideAsset(assetId, d);
    return api.getProject(project.id);
  });
  const genStoryboard = () => run("storyboard", () => api.generateStoryboard(project.id));
  const genFrame = (shotId) => run("frame:" + shotId, async () => {
    await api.generateFrame(shotId);
    return api.getProject(project.id);
  });
  const decideShot = (shotId, d) => run("shot", async () => {
    await api.decideShot(shotId, d);
    return api.getProject(project.id);
  });
  const shotsCount = project.scenes.reduce((n, s) => n + (s.shots?.length || 0), 0);
  const toggleStage = (key) => setOpenStage(openStage === key ? null : key);
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
  const assemble = () => run("assemble", async () => {
    await api.assembleProject(project.id);
    return api.getProject(project.id);
  });

  const toggleRec = async () => {
    if (rec) { mediaRef.current?.stop(); return; }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mr = new MediaRecorder(stream);
    const chunks = [];
    mr.ondataavailable = (e) => chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setBusy("stt");
      try {
        const { text } = await api.transcribe(new Blob(chunks, { type: "audio/webm" }));
        setIdea((prev) => (prev ? prev + " " : "") + text);
      } catch (e) { alert("STT: " + e.message); } finally { setBusy(""); }
    };
    mediaRef.current = mr;
    mr.start();
    setRec(true);
    mr.addEventListener("stop", () => setRec(false));
  };

  return (
    <div className="project">
      <div className="topline">
        <h2 className="pname">{project.title}</h2>
        <span className="cost">≈ ${project.cost_usd ?? 0} · API</span>
      </div>

      <Flow items={BRANCH} open={openStage} onToggle={toggleStage} statusOf={stageStatus} />
      {openStage === "idea" && (
      <div className="stage-panel">
        <textarea rows={3} value={idea} onChange={(e) => setIdea(e.target.value)}
          placeholder="Опиши идею ролика — текстом или голосом…" />
        <div className="row">
          <button onClick={toggleRec} className={rec ? "rec" : ""}>
            {rec ? "⏹ Стоп" : "🎤 Голос"}
          </button>
          <button className="primary" disabled={!idea.trim() || busy} onClick={saveIdea}>
            {busy === "idea" ? "…" : "Сохранить идею"}
          </button>
          {busy === "stt" && <span className="muted">распознаю…</span>}
        </div>
      </div>
      )}

      {openStage === "script" && (
      <div className="stage-panel">
        {project.logline && <p className="logline">«{project.logline}»</p>}
        <button className="primary" disabled={!project.brief_text || busy} onClick={genScript}>
          {busy === "script" ? "Генерирую…" : project.scenes.length ? "Перегенерировать" : "Сгенерировать сценарий"}
        </button>

        {project.scenes.map((s) => (
          <div key={s.id} className={`scene ${s.status}`}>
            <div className="scene-head">
              <b>Сцена {s.order}</b>
              <span className={`tag ${s.status}`}>{s.status}</span>
            </div>
            {editKey === "scene:" + s.id ? (
              editBox((t) => api.editScene(s.id, t))
            ) : (
              <>
                <pre>{s.script_text}</pre>
                <div className="row">
                  <button onClick={() => startEdit("scene:" + s.id, s.script_text)}>✎ Править</button>
                  <button onClick={() => decide(s.id, "approve")}>✓ Ок</button>
                  <button onClick={() => decide(s.id, "reject")}>✕ Переделать</button>
                </div>
              </>
            )}
          </div>
        ))}

        {project.scenes.length > 0 && (
          <div className="revise">
            <textarea rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)}
              placeholder="Правки ко всему сценарию (напр. «сделай динамичнее, убери сцену 3»)…" />
            <button disabled={!feedback.trim() || busy} onClick={revise}>Внести правки</button>
          </div>
        )}
      </div>
      )}

      {openStage === "style" && (
      <div className="stage-panel">
        {project.concepts.length === 0 ? (
          <button className="primary" disabled={!project.scenes.length || busy} onClick={extractVisuals}>
            {busy === "visuals" ? "Извлекаю…" : "Извлечь визуалы из сценария"}
          </button>
        ) : (
          <>
            <button disabled={busy} onClick={extractVisuals}>
              {busy === "visuals" ? "…" : "↻ Пересобрать визуалы"}
            </button>
            <div className="concepts">
              {project.concepts.map((c) => (
                <div key={c.id} className={`concept ${c.approved ? "approved" : ""}`}>
                  <div className="concept-media">
                    {c.url ? <img src={c.url} alt={c.name} /> : <div className="ph">нет картинки</div>}
                    <span className={`kind ${c.kind}`}>
                      {c.kind === "character" ? "персонаж" : "окружение"}
                    </span>
                  </div>
                  <div className="concept-body">
                    <b>{c.name}</b>
                    {editKey === "concept:" + c.id ? (
                      editBox((t) => api.editConcept(c.id, t))
                    ) : (
                      <>
                        <p className="cprompt">{c.prompt}</p>
                        <div className="row">
                          <button disabled={busy} onClick={() => genConcept(c.id)}>
                            {busy === "concept:" + c.id ? "Генерирую…" : c.url ? "↻ Перегенерировать" : "Сгенерировать"}
                          </button>
                          <button onClick={() => startEdit("concept:" + c.id, c.prompt)}>✎</button>
                          {c.url && (
                            <>
                              <button onClick={() => decideConcept(c.id, "approve")}>✓</button>
                              <button onClick={() => decideConcept(c.id, "reject")}>✕</button>
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
        )}
      </div>
      )}

      {openStage === "storyboard" && (
      <div className="stage-panel wide">
        {shotsCount === 0 ? (
          <button className="primary" disabled={!project.scenes.length || busy} onClick={genStoryboard}>
            {busy === "storyboard" ? "Раскадровываю…" : "Сделать раскадровку"}
          </button>
        ) : (
          <>
            <button disabled={busy} onClick={genStoryboard}>
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
                        {editKey === "shot:" + sh.id ? (
                          editBox((t) => api.patchShot(sh.id, { description: t }))
                        ) : (
                          <>
                            <p className="shot-desc">{sh.description}</p>
                            <div className="shot-meta">
                              <span>🎥 {sh.camera}</span>
                              <span>💡 {sh.lighting}</span>
                            </div>
                            <div className="row">
                              <button disabled={busy} onClick={() => genFrame(sh.id)}>
                                {busy === "frame:" + sh.id ? "…" : sh.frame_url ? "↻ Кадр" : "Кадр"}
                              </button>
                              <button onClick={() => startEdit("shot:" + sh.id, sh.description)}>✎</button>
                              <button onClick={() => decideShot(sh.id, "approve")}>✓</button>
                              <button onClick={() => decideShot(sh.id, "reject")}>✕</button>
                              <button className={openShot === sh.id ? "primary" : ""}
                                onClick={() => setOpenShot(openShot === sh.id ? null : sh.id)}>⚙ Элементы</button>
                            </div>
                          </>
                        )}
                      </div>
                      {openShot === sh.id && (
                        <ShotEditor shot={sh} voices={voices} presets={presets}
                          projectId={project.id} onChange={onChange} />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
      )}

      {openStage === "assembly" && (
      <div className="stage-panel">
        <button className="primary" disabled={shotsCount === 0 || busy} onClick={assemble}>
          {busy === "assemble" ? "Собираю…" : project.final_url ? "↻ Пересобрать ролик" : "Собрать ролик"}
        </button>
        <p className="hint" style={{ marginTop: 8 }}>
          Склейка шотов + сведение звука (голос/музыка/SFX) через ffmpeg. Видео шотов —
          Higgsfield (ждёт баланс); без видео шот берётся как статичный кадр.
        </p>
        {project.final_url && (
          <video controls src={project.final_url} style={{ width: "100%", maxWidth: 640, marginTop: 12, borderRadius: 10 }} />
        )}
      </div>
      )}
    </div>
  );
}

function Flow({ items, open, onToggle, statusOf }) {
  return (
    <div className="flow">
      {items.map((st, i) => (
        <Fragment key={st.key}>
          <button
            className={`fnode ${open === st.key ? "open" : ""} ${statusOf(st.key)}`}
            onClick={() => onToggle(st.key)}
          >
            <span className="fnode-n">{statusOf(st.key) === "done" ? "✓" : st.n}</span>
            <span className="fnode-title">{st.title}</span>
          </button>
          {i < items.length - 1 && <span className="farrow" />}
        </Fragment>
      ))}
    </div>
  );
}

function ShotEditor({ shot, voices, presets, projectId, onChange }) {
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
    } catch (e) {
      alert(element + ": " + e.message);
    } finally {
      setBusy("");
    }
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
