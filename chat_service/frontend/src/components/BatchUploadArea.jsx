import { useRef, useState } from "react";
import { createBatchTask } from "../api/taskApi.js";

const ALLOWED = [".pdf", ".docx", ".doc", ".html", ".htm", ".txt", ".md", ".rst"];

function valid(file) {
  const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  return file.size > 0 && ALLOWED.includes(ext);
}

async function readEntry(entry, parent = "") {
  if (entry.isFile) {
    return new Promise((resolve) => entry.file((file) => resolve([{ file, relativePath: `${parent}${file.name}` }])));
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    const entries = [];
    while (true) {
      const batch = await new Promise((resolve) => reader.readEntries(resolve));
      if (!batch.length) break;
      entries.push(...batch);
    }
    const nested = await Promise.all(entries.map((child) => readEntry(child, `${parent}${entry.name}/`)));
    return nested.flat();
  }
  return [];
}

export default function BatchUploadArea({ onOpenTasks }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  function normalize(list) {
    const selected = list.filter(({ file }) => valid(file));
    setFiles(selected);
    setMessage(selected.length ? `${selected.length} 个文件待上传` : "没有找到支持的文件");
  }

  async function handleDrop(event) {
    event.preventDefault(); setDragOver(false);
    const entries = [...(event.dataTransfer.items || [])].map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
    if (entries.length) normalize((await Promise.all(entries.map((entry) => readEntry(entry)))).flat());
    else normalize([...event.dataTransfer.files].map((file) => ({ file, relativePath: file.name })));
  }

  function handleInput(event) {
    normalize([...event.target.files].map((file) => ({ file, relativePath: file.webkitRelativePath || file.name })));
    event.target.value = "";
  }

  async function upload() {
    if (!files.length) return;
    setBusy(true); setMessage("正在上传文件...");
    try {
      const task = await createBatchTask(files);
      setFiles([]); setMessage(`任务已创建：${task.task_id}`); onOpenTasks?.();
    } catch (err) { setMessage(err.message); } finally { setBusy(false); }
  }

  return <section className="batch-upload">
    <div className="batch-upload__head"><div><h2>批量导入</h2><p>拖动一个目录，所有文件会作为一个异步任务处理。</p></div><button className="batch-upload__link" onClick={onOpenTasks}>查看任务</button></div>
    <div className={`batch-upload__dropzone ${dragOver ? "is-over" : ""}`} onDragOver={(e) => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)} onDrop={handleDrop} onClick={() => inputRef.current?.click()}>
      <div className="batch-upload__icon">▦</div><strong>拖动目录到这里</strong><span>或点击选择目录 · 支持 PDF、DOCX、TXT、Markdown、HTML、RST</span>
      <input ref={inputRef} type="file" webkitdirectory="true" directory="true" multiple onChange={handleInput} hidden />
    </div>
    {message && <div className="batch-upload__message">{message}</div>}
    {files.length > 0 && <div className="batch-upload__preview"><span>{files.length} 个文件已准备</span><button className="batch-upload__button" disabled={busy} onClick={upload}>{busy ? "上传中..." : "开始批量上传"}</button></div>}
  </section>;
}
