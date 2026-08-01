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
  reviseScript: (id, feedback) =>
    fetch(`/api/projects/${id}/script:revise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback }),
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
