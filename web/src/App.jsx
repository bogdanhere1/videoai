import { useEffect, useState } from "react";
import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";

// Пайплайн-граф проекта (крупный уровень). Детальный шот-граф — Фаза 4.
const STAGES = [
  { id: "idea", label: "1 · Идея" },
  { id: "script", label: "2 · Сценарий" },
  { id: "style", label: "3 · Визуал-стиль" },
  { id: "storyboard", label: "4 · Раскадровка" },
  { id: "shots", label: "5 · Шот-продакшн" },
  { id: "assembly", label: "6 · Сборка" },
];

const nodes = STAGES.map((s, i) => ({
  id: s.id,
  data: { label: s.label },
  position: { x: 40 + i * 200, y: 120 },
  style: {
    padding: 10,
    borderRadius: 10,
    border: "1px solid #6366f1",
    background: "#1e1b4b",
    color: "#e0e7ff",
    fontSize: 13,
  },
}));

const edges = STAGES.slice(1).map((s, i) => ({
  id: `e${i}`,
  source: STAGES[i].id,
  target: s.id,
  animated: true,
}));

export default function App() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: "api offline" }));
  }, []);

  return (
    <div className="app">
      <header>
        <h1>AI Video Studio</h1>
        <span className="badge">
          API: {health ? health.status : "…"}
          {health?.video_provider ? ` · provider: ${health.video_provider}` : ""}
        </span>
      </header>
      <div className="canvas">
        <ReactFlow nodes={nodes} edges={edges} fitView>
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
