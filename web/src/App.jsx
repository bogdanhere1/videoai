import { useEffect, useRef, useState } from "react";
import { api } from "./api";

const STAGES = ["idea", "script", "style", "storyboard", "shots", "assembly"];
const STAGE_LABEL = {
  idea: "Идея", script: "Сценарий", style: "Стиль",
  storyboard: "Раскадровка", shots: "Шоты", assembly: "Сборка",
};

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

function StageBar({ stage }) {
  const idx = STAGES.indexOf(stage);
  return (
    <div className="stagebar">
      {STAGES.map((s, i) => (
        <span key={s} className={`step ${i <= idx ? "done" : ""} ${i === idx ? "cur" : ""}`}>
          {i + 1}·{STAGE_LABEL[s]}
        </span>
      ))}
    </div>
  );
}

function Project({ project, onChange, afterChange }) {
  const [idea, setIdea] = useState(project.brief_text || "");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState("");
  const [rec, setRec] = useState(false);
  const mediaRef = useRef(null);

  useEffect(() => { setIdea(project.brief_text || ""); }, [project.id]);

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
      <StageBar stage={project.stage} />

      <section>
        <h2>1 · Идея</h2>
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
      </section>

      <section>
        <h2>2 · Сценарий</h2>
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
            <pre>{s.script_text}</pre>
            <div className="row">
              <button onClick={() => decide(s.id, "approve")}>✓ Ок</button>
              <button onClick={() => decide(s.id, "reject")}>✕ Переделать</button>
            </div>
          </div>
        ))}

        {project.scenes.length > 0 && (
          <div className="revise">
            <textarea rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)}
              placeholder="Правки ко всему сценарию (напр. «сделай динамичнее, убери сцену 3»)…" />
            <button disabled={!feedback.trim() || busy} onClick={revise}>Внести правки</button>
          </div>
        )}
      </section>
    </div>
  );
}
