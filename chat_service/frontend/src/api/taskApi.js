async function request(url, options = {}) {
  const res = await fetch(url, options);
  const body = await res.json();
  if (!res.ok) throw new Error(body?.detail?.message || body?.detail || `HTTP ${res.status}`);
  return body;
}

export async function listTasks() {
  return request("/api/tasks");
}

export async function getTask(taskId) {
  return request(`/api/tasks/${taskId}`);
}

export async function retryTask(taskId) {
  return request(`/api/tasks/${taskId}/retry`, { method: "POST" });
}

export async function createBatchTask(files) {
  const form = new FormData();
  const relativePaths = [];
  files.forEach(({ file, relativePath }) => {
    form.append("files", file, file.name);
    relativePaths.push(relativePath || file.webkitRelativePath || file.name);
  });
  form.append("relative_paths", JSON.stringify(relativePaths));
  return request("/api/tasks/batch-import", { method: "POST", body: form });
}
