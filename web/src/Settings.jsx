import { useEffect, useState } from "react";
import { api } from "./api";

// Этапы + какая категория моделей на них уместна (см. api/app/catalog.py)
const STAGES = [
  { key: "idea", title: "1 · Идея", hint: "распознавание речи / LLM" },
  { key: "script", title: "2 · Сценарий", hint: "LLM-сценарист" },
  { key: "style", title: "3 · Визуал-стиль", hint: "генерация картинок" },
  { key: "storyboard", title: "4 · Раскадровка", hint: "LLM + кадры" },
  { key: "shots", title: "5 · Шоты (видео/звук)", hint: "видео / липсинк / музыка" },
  { key: "assembly", title: "6 · Сборка", hint: "рендер" },
];
const KIND_HINT = {
  ad: "4–8 сцен, продукт в кадре, чёткий финальный план",
  social: "вертикаль 9:16, хук в первые 2 с, быстрый темп",
  explainer: "последовательное объяснение, спокойная камера",
  story: "драматургия, персонажи, диалог",
  music: "ритм, монтаж под бит, визуальные образы",
  intro: "5–10 с, лого/название в финале",
};

export default function SettingsDrawer({ project, catalog, onClose, onProjectChange }) {
  const projectId = project.id;
  const [cfg, setCfg] = useState(null);
  const [saved, setSaved] = useState("");
  const [fmt, setFmt] = useState({ ...(catalog?.format_defaults || {}), ...(project.format || {}) });
  const [title, setTitle] = useState(project.title || "");

  useEffect(() => {
    api.getSettings(projectId).then(setCfg).catch(() => setCfg({}));
  }, [projectId]);

  const upd = (stage, field, val) =>
    setCfg((c) => ({ ...c, [stage]: { ...c[stage], [field]: val } }));

  const save = async (stage) => {
    try {
      await api.putSetting(projectId, stage, cfg[stage]);
      setSaved(stage);
      setTimeout(() => setSaved(""), 1500);
    } catch (e) { alert("Ошибка: " + e.message); }
  };
  const saveFormat = async () => {
    try {
      const p = await api.patchProject(projectId, {
        title,
        format: { ...fmt, shot_duration: Number(fmt.shot_duration), target_seconds: Number(fmt.target_seconds) },
      });
      onProjectChange?.(p);
      setSaved("format");
      setTimeout(() => setSaved(""), 1500);
    } catch (e) { alert("Ошибка: " + e.message); }
  };

  const modelsFor = (stage) => {
    const cat = catalog?.stage_category?.[stage];
    if (!catalog || !cat || cat === "none") return [];
    return catalog[cat] || [];
  };

  return (
    <div className="drawer-scrim" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <h2>Настройки</h2>
          <button onClick={onClose}>✕</button>
        </div>

        <div className="drawer-section">
          <h3>Формат ролика</h3>
          <p className="muted">Задаёт кадр, качество и темп для всех этапов: сценарист учитывает формат,
            картинки и видео генерируются в нужной пропорции.</p>
          <div className="fmt-grid">
            <label>Название
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>Тип ролика
              <select value={fmt.kind || "ad"} onChange={(e) => setFmt({ ...fmt, kind: e.target.value })}>
                {(catalog?.project_kinds || []).map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
              </select>
            </label>
            <label>Кадр (aspect)
              <select value={fmt.aspect_ratio || "16:9"} onChange={(e) => setFmt({ ...fmt, aspect_ratio: e.target.value })}>
                {(catalog?.aspects || ["16:9"]).map((a) => <option key={a}>{a}</option>)}
              </select>
            </label>
            <label>Картинки
              <select value={fmt.resolution || "1K"} onChange={(e) => setFmt({ ...fmt, resolution: e.target.value })}>
                {(catalog?.image_res || ["1K"]).map((r) => <option key={r}>{r}</option>)}
              </select>
            </label>
            <label>Видео по умолчанию
              <select value={fmt.video_quality || "720p"} onChange={(e) => setFmt({ ...fmt, video_quality: e.target.value })}>
                {(catalog?.video_quality || ["720p"]).map((q) => (
                  <option key={q} value={q}>{q}{q === "draft" ? " — черновик 480p, ~3× дешевле" : ""}</option>
                ))}
              </select>
            </label>
            <label>Шот, с (мин. 4)
              <input type="number" min="4" max="30" value={fmt.shot_duration ?? 5}
                onChange={(e) => setFmt({ ...fmt, shot_duration: e.target.value })} />
            </label>
            <label>Целевая длительность, с
              <input type="number" min="5" max="600" value={fmt.target_seconds ?? 30}
                onChange={(e) => setFmt({ ...fmt, target_seconds: e.target.value })} />
            </label>
          </div>
          <p className="hint">{KIND_HINT[fmt.kind] || ""}</p>
          <div className="row">
            <button className="primary" onClick={saveFormat}>{saved === "format" ? "✓ Сохранено" : "Сохранить формат"}</button>
          </div>
        </div>

        <div className="drawer-section">
          <h3>Подключение нейросетей по этапам</h3>
          <p className="muted">
            По умолчанию: картинки/видео/музыка — Krea (если задан ключ в .env), иначе Higgsfield;
            голос/SFX — ElevenLabs; сценарий — Gemini. Включённый этап использует выбранного провайдера и модель.
            Ключ можно не вводить — тогда берётся ключ из .env сервера.
          </p>
        </div>

        {!cfg ? (
          <p className="muted">Загрузка…</p>
        ) : (
          STAGES.map((st) => {
            const s = cfg[st.key] || {};
            const models = modelsFor(st.key);
            const known = !s.model || models.some((m) => m.id === s.model);
            return (
              <div key={st.key} className={`api-card ${s.enabled ? "on" : ""}`}>
                <div className="api-head">
                  <div>
                    <b>{st.title}</b>
                    <span className="muted"> · {st.hint}</span>
                  </div>
                  <label className="switch">
                    <input type="checkbox" checked={!!s.enabled}
                      onChange={(e) => upd(st.key, "enabled", e.target.checked)} />
                    <span>{s.enabled ? "вкл" : "выкл"}</span>
                  </label>
                </div>
                <div className="api-grid">
                  <select value={s.provider || ""} onChange={(e) => upd(st.key, "provider", e.target.value)}>
                    {(catalog?.providers || [{ id: "", name: "по умолчанию" }]).map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                  {models.length > 0 ? (
                    <select value={known ? s.model || "" : "__custom"}
                      onChange={(e) => upd(st.key, "model", e.target.value === "__custom" ? "custom/model-id" : e.target.value)}>
                      <option value="">модель по умолчанию</option>
                      {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                      <option value="__custom">другая (вписать id)</option>
                    </select>
                  ) : (
                    <input placeholder="модель" value={s.model || ""}
                      onChange={(e) => upd(st.key, "model", e.target.value)} />
                  )}
                  {models.length > 0 && !known && (
                    <input placeholder="id модели, напр. kling/kling-4" value={s.model || ""}
                      onChange={(e) => upd(st.key, "model", e.target.value)} />
                  )}
                  <input placeholder="base URL (необязательно)" value={s.base_url || ""}
                    onChange={(e) => upd(st.key, "base_url", e.target.value)} />
                  <input type="password" placeholder="API-ключ (пусто = ключ из .env)" value={s.api_key || ""}
                    onChange={(e) => upd(st.key, "api_key", e.target.value)} />
                </div>
                <div className="row">
                  <button className="primary" onClick={() => save(st.key)}>
                    {saved === st.key ? "✓ Сохранено" : "Сохранить"}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
