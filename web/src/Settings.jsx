import { useEffect, useState } from "react";
import { api } from "./api";

// Этапы + подсказки, какой провайдер обычно уместен
const STAGES = [
  { key: "idea", title: "1 · Идея", hint: "распознавание речи / LLM", ph: "gemini · openai · custom" },
  { key: "script", title: "2 · Сценарий", hint: "LLM-сценарист", ph: "gemini · openai · anthropic · custom" },
  { key: "style", title: "3 · Визуал-стиль", hint: "генерация картинок", ph: "higgsfield · custom" },
  { key: "storyboard", title: "4 · Раскадровка", hint: "LLM + кадры", ph: "gemini · higgsfield · custom" },
  { key: "shots", title: "5 · Шоты (видео/звук)", hint: "видео/голос/музыка", ph: "higgsfield · elevenlabs · custom" },
  { key: "assembly", title: "6 · Сборка", hint: "рендер", ph: "ffmpeg · custom" },
];

export default function SettingsDrawer({ projectId, onClose }) {
  const [cfg, setCfg] = useState(null);
  const [saved, setSaved] = useState("");

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

  return (
    <div className="drawer-scrim" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <h2>Настройки</h2>
          <button onClick={onClose}>✕</button>
        </div>

        <div className="drawer-section">
          <h3>Подключение нейросетей по этапам</h3>
          <p className="muted">
            На каждом этапе можно подключить свою нейросеть через API. Включённый этап
            использует ваш провайдер вместо стандартного.
          </p>
        </div>

        {!cfg ? (
          <p className="muted">Загрузка…</p>
        ) : (
          STAGES.map((st) => {
            const s = cfg[st.key] || {};
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
                  <input placeholder={"провайдер: " + st.ph} value={s.provider || ""}
                    onChange={(e) => upd(st.key, "provider", e.target.value)} />
                  <input placeholder="модель (напр. gpt-4o, gemini-3.1-flash-lite)" value={s.model || ""}
                    onChange={(e) => upd(st.key, "model", e.target.value)} />
                  <input placeholder="base URL (напр. https://api.openai.com/v1)" value={s.base_url || ""}
                    onChange={(e) => upd(st.key, "base_url", e.target.value)} />
                  <input type="password" placeholder="API-ключ" value={s.api_key || ""}
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
