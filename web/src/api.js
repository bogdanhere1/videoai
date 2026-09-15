const j = (r) => {
  if (!r.ok) return r.text().then((t) => Promise.reject(new Error(t || r.status)));
  return r.json();
};

export const api = {
  health: () => fetch("/health").then(j),
  listProjects: () => fetch("/api/projects").then(j),
  createProject: (title) =>
    fetch(`/api/projects?title=${encodeURIComponent(title)}`, { method: "POST" }).then(j),
  getProject: (id) => fetch(`/api/projects/${id}`).then(j),
  setIdea: (id, text) =>
    fetch(`/api/projects/${id}/idea`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then(j),
  generateScript: (id) =>
    fetch(`/api/projects/${id}/script:generate`, { method: "POST" }).then(j),
  editScene: (sceneId, script_text) =>
    fetch(`/api/scenes/${sceneId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script_text }),
    }).then(j),
  reviseScript: (id, feedback) =>
    fetch(`/api/projects/${id}/script:revise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback }),
    }).then(j),
  assembleProject: (id) =>
    fetch(`/api/projects/${id}/assemble`, { method: "POST" }).then(j),
  listModifiers: (id) => fetch(`/api/projects/${id}/modifiers`).then(j),
  createModifier: (id, kind = "style", target_stage = "storyboard") =>
    fetch(`/api/projects/${id}/modifiers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, target_stage }),
    }).then(j),
  patchModifier: (mid, patch) =>
    fetch(`/api/modifiers/${mid}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).then(j),
  uploadReference: (mid, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`/api/modifiers/${mid}/reference`, { method: "POST", body: fd }).then(j);
  },
  deleteModifier: (mid) => fetch(`/api/modifiers/${mid}`, { method: "DELETE" }).then(j),
  getSettings: (id) => fetch(`/api/projects/${id}/settings`).then(j),
  putSetting: (id, stage, cfg) =>
    fetch(`/api/projects/${id}/settings/${stage}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    }).then(j),
  getVoices: () => fetch("/api/voices").then(j),
  getCameraPresets: () => fetch("/api/camera-presets").then(j),
  patchShot: (shotId, patch) =>
    fetch(`/api/shots/${shotId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).then(j),
  genShotElement: (shotId, element) =>
    fetch(`/api/shots/${shotId}/${element}:generate`, { method: "POST" }).then(j),
  generateStoryboard: (id) =>
    fetch(`/api/projects/${id}/storyboard:generate`, { method: "POST" }).then(j),
  generateFrame: (shotId) =>
    fetch(`/api/shots/${shotId}:frame`, { method: "POST" }).then(j),
  decideShot: (shotId, decision, note = "") =>
    fetch(`/api/shots/${shotId}/${decision}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    }).then(j),
  extractVisuals: (id) =>
    fetch(`/api/projects/${id}/visuals:extract`, { method: "POST" }).then(j),
  generateConcept: (assetId) =>
    fetch(`/api/concepts/${assetId}:generate`, { method: "POST" }).then(j),
  editConcept: (assetId, prompt) =>
    fetch(`/api/concepts/${assetId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    }).then(j),
  decideAsset: (assetId, decision, note = "") =>
    fetch(`/api/assets/${assetId}/${decision}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    }).then(j),
  decideScene: (sceneId, decision, note = "") =>
    fetch(`/api/scenes/${sceneId}/${decision}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    }).then(j),
  transcribe: (blob) => {
    const fd = new FormData();
    fd.append("file", blob, "idea.webm");
    return fetch("/api/transcribe", { method: "POST", body: fd }).then(j);
  },
};
