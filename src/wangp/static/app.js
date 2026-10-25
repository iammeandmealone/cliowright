const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || res.statusText);
  }
  return data;
}

async function loadHealth() {
  const el = $("health");
  try {
    const data = await api("/api/health");
    if (data.instructor) {
      el.textContent = `instructor ready  ${data.model}  ${data.base_url}`;
      el.className = "health ok";
    } else {
      el.textContent = "instructor offline  set USER_LLM_API_KEY in .env";
      el.className = "health bad";
    }
  } catch (err) {
    el.textContent = `health failed  ${err.message}`;
    el.className = "health bad";
  }
}

async function loadSettings() {
  const data = await api("/api/settings");
  const root = $("fields");
  root.innerHTML = "";
  for (const field of data.fields) {
    const div = document.createElement("div");
    div.className = "field";
    div.innerHTML = `<strong>${field.label}</strong> <code>${field.key}</code><div class="help">${field.help}</div>`;
    root.appendChild(div);
  }
}

function renderShots(script) {
  const root = $("shots");
  const shots = (script && script.shots) || [];
  if (!shots.length) {
    root.className = "shots empty";
    root.textContent = "No shots parsed.";
    return;
  }
  root.className = "shots";
  root.innerHTML = "";
  if (script.defaults && Object.keys(script.defaults).length) {
    const def = document.createElement("div");
    def.className = "shot";
    def.innerHTML = `<h3>Defaults</h3><div class="meta">${Object.entries(script.defaults).map(([k, v]) => `${k}=${v}`).join("  ")}</div>`;
    root.appendChild(def);
  }
  shots.forEach((shot, i) => {
    const div = document.createElement("div");
    div.className = "shot";
    const meta = Object.entries(shot)
      .filter(([k]) => !["id", "title", "prompt"].includes(k))
      .map(([k, v]) => `${k}=${v}`)
      .join("  ");
    div.innerHTML = `<h3>${i + 1}. ${shot.title || shot.id}</h3><p>${shot.prompt || ""}</p>${meta ? `<div class="meta">${meta}</div>` : ""}`;
    root.appendChild(div);
  });
}

function renderJobs(jobs) {
  const root = $("jobs");
  if (!jobs.length) {
    root.className = "jobs empty";
    root.textContent = "No jobs yet.";
    return;
  }
  root.className = "jobs";
  root.innerHTML = "";
  jobs.forEach((job) => {
    const div = document.createElement("div");
    div.className = "job";
    const files = (job.outputs || []).join(", ");
    div.innerHTML = `<span class="id">${job.id}</span><span>${job.title || "script"} ${files ? " / " + files : ""} ${job.error || ""}</span><span class="badge ${job.status}">${job.status}</span>`;
    root.appendChild(div);
  });
}

async function refreshJobs() {
  const data = await api("/api/jobs");
  renderJobs(data.jobs || []);
}

async function parseScript() {
  const text = $("script").value;
  const data = await api("/api/script/parse", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  if (data.markdown) $("script").value = data.markdown;
  renderShots(data.script);
  $("script-status").textContent = `${data.script.shots.length} shot(s)  pipeline ${data.pipeline.steps.length} step(s)`;
  $("script-status").className = "status";
  return data;
}

async function run(dryRun) {
  $("script-status").textContent = dryRun ? "dry-run..." : "running...";
  try {
    const parsed = await parseScript();
    const data = await api("/api/run", {
      method: "POST",
      body: JSON.stringify({ script: parsed.script, dry_run: dryRun }),
    });
    $("script-status").textContent = `job ${data.job.id} ${data.job.status}`;
    await refreshJobs();
  } catch (err) {
    $("script-status").textContent = err.message;
    $("script-status").className = "status err";
  }
}

async function draft(revise) {
  const brief = $("brief").value.trim();
  if (!brief) {
    $("instruct-status").textContent = "brief required";
    $("instruct-status").className = "status err";
    return;
  }
  $("instruct-status").textContent = "instructor working...";
  $("instruct-status").className = "status";
  $("btn-instruct").disabled = true;
  $("btn-revise").disabled = true;
  try {
    const data = await api("/api/instruct", {
      method: "POST",
      body: JSON.stringify({
        brief,
        notes: $("notes").value,
        script: revise ? $("script").value : null,
      }),
    });
    $("script").value = data.markdown || "";
    renderShots(data.script);
    $("instruct-status").textContent = `drafted with ${data.model}`;
  } catch (err) {
    $("instruct-status").textContent = err.message;
    $("instruct-status").className = "status err";
  } finally {
    $("btn-instruct").disabled = false;
    $("btn-revise").disabled = false;
  }
}

$("btn-instruct").addEventListener("click", () => draft(false));
$("btn-revise").addEventListener("click", () => draft(true));
$("btn-parse").addEventListener("click", () => parseScript().catch((err) => {
  $("script-status").textContent = err.message;
  $("script-status").className = "status err";
}));
$("btn-dry").addEventListener("click", () => run(true));
$("btn-run").addEventListener("click", () => run(false));

loadHealth();
loadSettings();
refreshJobs();
setInterval(refreshJobs, 3000);
