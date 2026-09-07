import { useEffect, useMemo, useState } from "react";
import { getTask, listTasks, retryTask } from "../api/taskApi.js";

const STAGES = [
  { key: "upload", label: "Stage 1 · Upload Files", description: "Files written to the server temporary directory" },
  { key: "processing", label: "Stage 2 · Convert and Vectorize", description: "OKF · taxonomy · BGE-M3 · ChromaDB" },
  { key: "complete", label: "Stage 3 · Results", description: "Classification and storage results" },
];

function statusLabel(status) {
  return { queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", duplicate: "Skipped (duplicate)" }[status] || status;
}

function stageState(task, key) {
  if (key === "upload") return task.uploaded_files >= task.total_files ? "done" : "active";
  if (key === "processing") return task.stage === "processing" ? "active" : task.stage === "complete" ? "done" : "pending";
  return task.stage === "complete" ? "done" : "pending";
}

export default function TaskPage() {
  const [tasks, setTasks] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedStage, setSelectedStage] = useState("processing");
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  async function refresh() {
    try {
      const rows = await listTasks();
      setTasks(rows);
      const id = selectedId || rows[0]?.task_id;
      if (id) {
        setSelectedId(id);
        setDetail(await getTask(id));
      }
      setError(null);
    } catch (err) { setError(err.message); }
  }

  useEffect(() => { refresh(); const timer = setInterval(refresh, 2500); return () => clearInterval(timer); }, [selectedId]);

  const selected = detail || tasks.find((task) => task.task_id === selectedId) || tasks[0];
  const running = useMemo(() => tasks.filter((task) => ["queued", "running"].includes(task.status)), [tasks]);
  const completed = useMemo(() => tasks.filter((task) => ["completed", "failed"].includes(task.status)), [tasks]);

  async function selectTask(taskId) {
    setSelectedId(taskId);
    setDetail(await getTask(taskId));
  }

  async function handleRetry() {
    if (!selected) return;
    await retryTask(selected.task_id);
    await refresh();
  }

  return (
    <div className="task-page">
      <header className="task-page__header">
        <div><h1>Tasks</h1><p>View running and completed batch import tasks.</p></div>
        {selected?.failed_files > 0 && <button className="task-page__retry" onClick={handleRetry}>Retry Failed Files</button>}
      </header>
      {error && <div className="task-page__error">{error}</div>}
      <div className="task-page__layout">
        <aside className="task-list">
          <h2>Running <span>{running.length}</span></h2>
          {running.map((task) => <TaskListItem key={task.task_id} task={task} selected={task.task_id === selected?.task_id} onClick={selectTask} />)}
          <h2 className="task-list__completed">Completed <span>{completed.length}</span></h2>
          {completed.map((task) => <TaskListItem key={task.task_id} task={task} selected={task.task_id === selected?.task_id} onClick={selectTask} />)}
          {!tasks.length && <p className="task-page__empty">No batch tasks yet.</p>}
        </aside>
        <section className="task-detail">
          {selected ? <TaskDetail task={selected} selectedStage={selectedStage} onStage={setSelectedStage} /> : <p className="task-page__empty">Select a task to view details.</p>}
        </section>
      </div>
    </div>
  );
}

function TaskListItem({ task, selected, onClick }) {
  return <button className={`task-list__item ${selected ? "is-selected" : ""}`} onClick={() => onClick(task.task_id)}>
    <span className={`task-list__dot task-list__dot--${task.status}`} />
    <span className="task-list__item-main"><strong>{task.task_id.slice(0, 12)}</strong><small>{statusLabel(task.status)} · {task.total_files} files</small></span>
    <b>{task.progress_percent}%</b>
  </button>;
}

function TaskDetail({ task, selectedStage, onStage }) {
  const files = task.files || [];
  return <>
    <div className="task-detail__top"><div><h2>{task.task_id}</h2><p>{task.created_at} · {statusLabel(task.status)}</p></div><span className={`task-detail__status task-detail__status--${task.status}`}>{statusLabel(task.status)}</span></div>
    <div className="task-stats"><Stat label="Total Files" value={task.total_files} /><Stat label="Completed" value={task.processed_files - task.failed_files} /><Stat label="Failed" value={task.failed_files} /><Stat label="Overall Progress" value={`${task.progress_percent}%`} progress={task.progress_percent} /></div>
    <div className="task-stages">{STAGES.map((stage, index) => <Stage key={stage.key} stage={stage} index={index} state={stageState(task, stage.key)} selected={selectedStage === stage.key} onClick={() => onStage(stage.key)} task={task} files={files} />)}</div>
  </>;
}

function Stat({ label, value, progress }) { return <div className="task-stat"><span>{label}</span><strong>{value}</strong>{progress !== undefined && <div className="task-progress"><i style={{ width: `${progress}%` }} /></div>}</div>; }

function Stage({ stage, index, state, selected, onClick, task, files }) {
  const stageFiles = stage.key === "upload" ? files.filter((file) => ["uploaded", "duplicate", "converting", "embedding", "completed", "failed"].includes(file.status)) : files;
  const complete = stage.key === "upload" ? task.uploaded_files : stage.key === "processing" ? task.processed_files : task.stage === "complete" ? task.total_files : 0;
  const percent = task.total_files ? Math.round((complete / task.total_files) * 100) : 0;
  return <article className={`task-stage task-stage--${state} ${selected ? "is-open" : ""}`}>
    <button className="task-stage__head" onClick={onClick}><span className="task-stage__number">{state === "done" ? "✓" : index + 1}</span><span><strong>{stage.label}</strong><small>{stage.description}</small></span><b>{complete} / {task.total_files}</b><span>›</span></button>
    {selected && <div className="task-stage__body"><div className="task-stage__meta"><span>{state === "done" ? "Completed" : "Current Progress"}</span><b>{percent}%</b></div><div className="task-progress"><i style={{ width: `${percent}%` }} /></div><div className="task-stage__files"><div className="task-stage__file-head"><span>File</span><span>Status</span><span>Classification / Storage</span></div>{stageFiles.slice(0, 40).map((file) => <div className="task-stage__file" key={file.file_id}><span title={file.relative_path}>{file.relative_path}</span><span className={`task-file-status task-file-status--${file.status}`}>{file.status}</span><span>{file.storage_path || file.category_level_3 || "—"}</span></div>)}</div></div>}
  </article>;
}
