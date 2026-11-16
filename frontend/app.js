(() => {
  "use strict";

  // ================= Elements =================
  const $ = (id) => document.getElementById(id);
  const els = {
    landing: $("landing"), chatApp: $("chatApp"), startBtn: $("startBtn"),
    recentGrid: $("recentGrid"), recentEmpty: $("recentEmpty"), clearAllBtn: $("clearAllBtn"),
    sidebar: $("sidebar"), scrim: $("scrim"), homeBtn: $("homeBtn"), newChatBtn: $("newChatBtn"),
    historyList: $("historyList"), openSidebarBtn: $("openSidebarBtn"), closeSidebarBtn: $("closeSidebarBtn"),
    chatTitle: $("chatTitle"), statusDot: $("statusDot"), statusText: $("statusText"),
    thread: $("thread"), emptyState: $("emptyState"), suggestions: $("suggestions"), messages: $("messages"),
    form: $("composer"), input: $("input"), sendBtn: $("sendBtn"),
  };

  // ================= Storage (chat history in this browser) =================
  // Chat shape: { id, title, createdAt, updatedAt, messages: [{ role, text, plan?, steps? }] }
  const STORE_KEY = "wanderly.chats.v1";

  function loadChats() {
    try {
      const data = JSON.parse(localStorage.getItem(STORE_KEY));
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  }

  function saveChats() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(chats));
    } catch {
      /* storage full or disabled: chats just won't persist */
    }
  }

  let chats = loadChats();   // newest first
  let current = null;        // chat being viewed (may be unsaved if empty)
  let busy = false;

  // ================= Groq usage panel =================
  // Numbers come from /api/limits (collected from normal Groq calls, so free to read).
  // Countdowns tick in the browser every second.
  const usageList = $("usageList");
  const usageRefresh = $("usageRefresh");
  let usage = null;        // last snapshot from the server
  let clockOffset = 0;     // server time − browser time (seconds)

  const nowSec = () => Date.now() / 1000 + clockOffset;

  function fmtLeft(at) {
    const secs = Math.max(0, Math.round(at - nowSec()));
    if (secs === 0) return "now";
    const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = secs % 60;
    return h ? `${h}h ${m}m` : m ? `${m}m ${s}s` : `${s}s`;
  }

  const fmtNum = (n) => (n ?? 0).toLocaleString();

  function usageRow(label, value, extra) {
    const row = el("div", "usage-row");
    const left = el("span", "", `${label}: `);
    left.append(el("b", "", value));
    row.append(left);
    if (extra) row.append(el("span", "", extra));
    return row;
  }

  function usageBar(left, limit) {
    const bar = el("div", "usage-bar");
    const fill = el("span");
    const pct = limit ? Math.max(0, Math.min(100, (left / limit) * 100)) : 0;
    fill.style.width = `${pct}%`;
    if (pct < 15) fill.classList.add("low");
    bar.append(fill);
    return bar;
  }

  function renderUsage() {
    if (!usage) return;
    usageList.replaceChildren();
    const now = nowSec();

    usage.models.forEach((m) => {
      const box = el("div", "usage-model");
      const name = el("div", "usage-name");
      name.append(el("span", "", m.model.replace(/^[^/]+\//, "")));

      const blocked = m.daily_blocked_until && m.daily_blocked_until > now;
      const badge = el("span", "usage-badge",
        blocked ? "Limit hit" : m.updated_at ? "OK" : "Not used yet");
      if (blocked) badge.classList.add("blocked");
      else if (!m.updated_at) badge.classList.add("idle");
      name.append(badge);
      box.append(name);

      if (blocked) {
        box.append(usageRow("Daily tokens", "used up", `back in ${fmtLeft(m.daily_blocked_until)}`));
      }
      if (m.requests_limit != null) {
        // Values age once their reset time passes, so show them as refilled.
        const reqLeft = m.requests_reset_at && m.requests_reset_at <= now ? m.requests_limit : m.requests_left;
        box.append(usageRow("Requests/day", `${fmtNum(reqLeft)} / ${fmtNum(m.requests_limit)}`,
          reqLeft < m.requests_limit && m.requests_reset_at ? `full in ${fmtLeft(m.requests_reset_at)}` : "full"));
        box.append(usageBar(reqLeft, m.requests_limit));
      }
      if (m.tpm_limit != null) {
        const tokLeft = m.tpm_reset_at && m.tpm_reset_at <= now ? m.tpm_limit : m.tpm_left;
        box.append(usageRow("Tokens/min", `${fmtNum(tokLeft)} / ${fmtNum(m.tpm_limit)}`,
          tokLeft < m.tpm_limit && m.tpm_reset_at ? `full in ${fmtLeft(m.tpm_reset_at)}` : "full"));
        box.append(usageBar(tokLeft, m.tpm_limit));
      }
      if (m.daily_tokens_limit) {
        box.append(usageRow("Daily tokens (last seen)",
          `${fmtNum(m.daily_tokens_used)} / ${fmtNum(m.daily_tokens_limit)}`));
      }
      if (m.updated_at) {
        box.append(usageRow("This session", `${fmtNum(m.session_tokens)} tokens`, `${m.session_calls} calls`));
      }
      usageList.append(box);
    });
  }

  async function loadUsage(refresh = false) {
    try {
      if (refresh) usageRefresh.classList.add("spin");
      const res = await fetch(refresh ? "/api/limits/refresh" : "/api/limits", { method: refresh ? "POST" : "GET" });
      if (!res.ok) return;
      usage = await res.json();
      clockOffset = usage.now - Date.now() / 1000;
      renderUsage();
    } catch { /* server offline: keep the last numbers */ }
    finally { usageRefresh.classList.remove("spin"); }
  }

  usageRefresh.addEventListener("click", (e) => {
    e.preventDefault(); // don't collapse the panel
    if (!busy) loadUsage(true);
  });
  setInterval(renderUsage, 1000);                       // tick countdowns
  setInterval(() => { if (!document.hidden) loadUsage(); }, 15000);
  loadUsage();

  // ================= Mode switch (Groq cloud / local Ollama) =================
  const MODE_KEY = "wanderly.mode";
  const modeSwitch = $("modeSwitch");
  const modeButtons = [...modeSwitch.querySelectorAll("button[data-mode]")];
  let modeLabels = { groq: "Groq · cloud", local: "Local" };
  let mode = localStorage.getItem(MODE_KEY) === "local" ? "local" : "groq";

  function setMode(next) {
    mode = next;
    try { localStorage.setItem(MODE_KEY, mode); } catch { /* ignore */ }
    modeButtons.forEach((btn) => {
      const on = btn.dataset.mode === mode;
      btn.setAttribute("aria-checked", String(on));
      btn.tabIndex = on ? 0 : -1;
      btn.title = modeLabels[btn.dataset.mode];
    });
  }

  modeButtons.forEach((btn) => btn.addEventListener("click", () => { if (!busy) setMode(btn.dataset.mode); }));
  modeSwitch.addEventListener("keydown", (e) => { // arrow keys move between options (radiogroup pattern)
    if (busy || !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault();
    const next = mode === "groq" ? "local" : "groq";
    setMode(next);
    modeButtons.find((b) => b.dataset.mode === next).focus();
  });

  // Server tells us the exact local model name (e.g. "Local · hermes3:3b").
  fetch("/api/modes").then((r) => r.json()).then((data) => {
    modeLabels = { ...modeLabels, ...data.modes };
    setMode(mode);
  }).catch(() => {});
  setMode(mode);

  function newChat() {
    const now = Date.now();
    // The id doubles as the LangGraph thread_id, so each chat keeps its own memory.
    return { id: crypto.randomUUID(), title: "New trip", createdAt: now, updatedAt: now, messages: [] };
  }

  function makeTitle(text) {
    const clean = text.replace(/\s+/g, " ").trim();
    return clean.length > 42 ? `${clean.slice(0, 42)}…` : clean;
  }

  function moveToTop(chat) {
    chats = [chat, ...chats.filter((c) => c !== chat)];
  }

  // ================= Small helpers =================
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function formatDate(ts) {
    return new Date(ts).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }

  // Progress line style: ✓ done, ↻ rework, → supervisor assigned an agent.
  function stepClass(kind) {
    return ["rework", "plan"].includes(kind) ? kind : "done";
  }

  function scrollToBottom() {
    els.thread.scrollTop = els.thread.scrollHeight;
  }

  // ================= Markdown (rendered + sanitized) =================
  marked.setOptions({ gfm: true, breaks: false });
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });

  function renderMarkdown(text) {
    const template = document.createElement("template");
    template.innerHTML = DOMPurify.sanitize(marked.parse(text));
    template.content.querySelectorAll("table").forEach((table) => {
      const wrap = el("div", "table-wrap");
      table.replaceWith(wrap);
      wrap.appendChild(table);
    });
    template.content.querySelectorAll('input[type="checkbox"]').forEach((box) => {
      box.disabled = false;
      box.setAttribute("aria-label", "Mark item as done");
    });
    return template.content;
  }

  // ================= Routing (#/ · #/new · #/chat/<id>) =================
  function go(hash) {
    if (location.hash === hash) route();
    else location.hash = hash;
  }

  function route() {
    const match = location.hash.match(/^#\/chat\/([A-Za-z0-9-]+)$/);
    if (location.hash === "#/new") showChat(null);
    else if (match) showChat(match[1]);
    else showLanding();
  }

  function showLanding() {
    els.chatApp.hidden = true;
    els.landing.hidden = false;
    document.body.classList.remove("in-chat");
    document.title = "Wanderly · AI Trip Planner";
    renderRecent();
  }

  function showChat(id) {
    current = (id && chats.find((c) => c.id === id)) || newChat();
    els.landing.hidden = true;
    els.chatApp.hidden = false;
    document.body.classList.add("in-chat");
    closeSidebar();
    renderThread();
    renderHistory();
    els.input.focus();
  }

  // ================= Landing: recent trips =================
  function renderRecent() {
    els.recentGrid.replaceChildren();
    const recent = chats.slice(0, 6);
    els.recentEmpty.hidden = recent.length > 0;
    els.clearAllBtn.hidden = chats.length === 0;

    recent.forEach((chat) => {
      const card = el("div", "recent-card glass");
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", `Open chat: ${chat.title}`);
      card.append(
        el("span", "recent-title", chat.title),
        el("span", "recent-meta", `${formatDate(chat.updatedAt)} · ${chat.messages.length} messages`),
      );

      const del = el("button", "recent-del", "✕");
      del.type = "button";
      del.setAttribute("aria-label", `Delete chat: ${chat.title}`);
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteChat(chat.id);
      });
      card.append(del);

      const open = () => go(`#/chat/${chat.id}`);
      card.addEventListener("click", open);
      card.addEventListener("keydown", (e) => {
        if (e.target !== card) return; // ignore keys on the delete button
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
      els.recentGrid.append(card);
    });
  }

  // ================= Sidebar: history =================
  function renderHistory() {
    els.historyList.replaceChildren();
    if (chats.length === 0) {
      els.historyList.append(el("p", "history-empty", "No chats yet"));
      return;
    }
    chats.forEach((chat) => {
      const item = el("div", "history-item");
      if (current && chat.id === current.id) item.classList.add("active");

      const open = el("button", "history-open", chat.title);
      open.type = "button";
      open.title = chat.title;
      if (item.classList.contains("active")) open.setAttribute("aria-current", "page");
      open.addEventListener("click", () => go(`#/chat/${chat.id}`));

      const del = el("button", "history-del", "✕");
      del.type = "button";
      del.setAttribute("aria-label", `Delete chat: ${chat.title}`);
      del.addEventListener("click", () => deleteChat(chat.id));

      item.append(open, del);
      els.historyList.append(item);
    });
  }

  function deleteChat(id) {
    if (busy) return;
    const chat = chats.find((c) => c.id === id);
    if (!chat || !confirm(`Delete "${chat.title}"?`)) return;
    chats = chats.filter((c) => c.id !== id);
    saveChats();
    if (current && current.id === id && !els.chatApp.hidden) go("#/new");
    else { renderHistory(); renderRecent(); }
  }

  // ================= Thread rendering =================
  function renderThread() {
    els.messages.replaceChildren();
    current.messages.forEach(renderMessage);
    els.emptyState.hidden = current.messages.length > 0;
    els.chatTitle.textContent = current.title;
    document.title = `${current.title} · Wanderly`;
    scrollToBottom();
  }

  function botRow() {
    const row = el("div", "msg bot");
    const avatar = el("div", "avatar", "🧭");
    avatar.setAttribute("aria-hidden", "true");
    row.append(avatar);
    const content = el("div", "content");
    row.append(content);
    return { row, content };
  }

  function renderMessage(m) {
    if (m.role === "user") {
      const row = el("div", "msg user");
      row.append(el("div", "bubble", m.text)); // plain text, never HTML
      els.messages.append(row);
      return;
    }

    const { row, content } = botRow();
    if (m.role === "error") {
      row.classList.add("error");
      content.textContent = m.text;
    } else {
      if (m.steps && m.steps.length > 1) content.append(makeTrace(m.steps));
      const md = el("div", "md");
      md.append(renderMarkdown(m.text));
      content.append(md);
      if (m.plan) content.append(makeActions(m.text));
      // Shows which mode wrote this answer, handy when comparing Groq vs local.
      if (m.mode) content.append(el("span", "mode-tag", m.mode === "local" ? "💻 Local" : "☁️ Groq"));
    }
    els.messages.append(row);
  }

  function makeTrace(steps) {
    const details = el("details", "trace");
    details.append(el("summary", "", `🔍 How this plan was made · ${steps.length} steps`));
    const list = el("ul", "progress");
    steps.forEach(({ text, kind }) => list.append(el("li", stepClass(kind), text)));
    details.append(list);
    return details;
  }

  function makeActions(text) {
    const bar = el("div", "msg-actions");

    const copy = el("button", "action-btn", "Copy");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(text); copy.textContent = "Copied ✓"; }
      catch { copy.textContent = "Copy failed"; }
      setTimeout(() => (copy.textContent = "Copy"), 1800);
    });

    const download = el("button", "action-btn", "Download .md");
    download.type = "button";
    download.addEventListener("click", () => {
      const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
      const a = el("a");
      a.href = url;
      a.download = `${(current?.title || "trip").replace(/[^\w\- ]+/g, "").trim() || "trip"}.md`;
      a.click();
      URL.revokeObjectURL(url);
    });

    bar.append(copy, download);
    return bar;
  }

  // Live progress row while the graph runs.
  function addProgress(chat) {
    const { row, content } = botRow();
    const list = el("ul", "progress");
    const active = el("li", "active", "Supervisor is reading your request…");
    list.append(active);
    content.append(list);
    els.messages.append(row);
    scrollToBottom();

    const steps = [];
    return {
      add(text, kind) {
        list.insertBefore(el("li", stepClass(kind), text), active);
        steps.push({ text, kind });
        active.textContent = "Team is working…";
        if (current === chat) scrollToBottom();
      },
      finish() {
        row.remove();
        return steps;
      },
    };
  }

  // Add a message to a chat, save it, and render it if that chat is open.
  function addToChat(chat, message) {
    chat.messages.push(message);
    chat.updatedAt = Date.now();
    moveToTop(chat);
    saveChats();
    if (current === chat && !els.chatApp.hidden) {
      els.emptyState.hidden = true;
      renderMessage(message);
      scrollToBottom();
    }
    renderHistory();
  }

  // ================= Networking =================
  async function readStream(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const handleLine = (line) => {
      if (!line.trim()) return;
      try { onEvent(JSON.parse(line)); } catch { /* ignore malformed line */ }
    };
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      lines.forEach(handleLine);
    }
    handleLine(buffer + decoder.decode());
  }

  async function send(text) {
    const message = text.trim();
    if (!message || busy) return;

    const chat = current;
    // First message: save the chat and give it a real URL.
    if (!chats.includes(chat)) {
      chat.title = makeTitle(message);
      chats.unshift(chat);
      history.replaceState(null, "", `#/chat/${chat.id}`);
      els.chatTitle.textContent = chat.title;
      document.title = `${chat.title} · Wanderly`;
    }

    const runMode = mode; // locked for this request, even if the switch changes later
    addToChat(chat, { role: "user", text: message });
    setBusy(true);
    const progress = addProgress(chat);

    let finalText = null;
    let errorText = null;
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: chat.id, mode: runMode }),
      });
      if (!response.ok) {
        throw new Error(response.status === 422
          ? "That message couldn't be processed. Please keep it under 2,000 characters."
          : `Server error (${response.status}). Please try again.`);
      }
      await readStream(response, (event) => {
        if (event.type === "status") progress.add(event.text, event.kind);
        else if (event.type === "final") finalText = event.text;
        else if (event.type === "error") errorText = event.text;
      });
    } catch (err) {
      errorText = err instanceof TypeError ? "Can't reach the server. Is it running?" : err.message;
    }

    const steps = progress.finish();
    if (errorText) addToChat(chat, { role: "error", text: errorText });
    else if (finalText) addToChat(chat, { role: "bot", text: finalText, plan: steps.length > 1, steps, mode: runMode });
    else addToChat(chat, { role: "error", text: "No response received. Please try again." });

    setBusy(false);
    loadUsage(); // numbers changed during the run
    if (!els.chatApp.hidden) els.input.focus();
  }

  // ================= UI state =================
  function setBusy(value) {
    busy = value;
    els.sendBtn.disabled = value;
    els.newChatBtn.disabled = value;
    modeButtons.forEach((btn) => (btn.disabled = value));
    els.statusDot.classList.toggle("busy", value);
    els.statusText.textContent = value ? "Planning…" : "Online";
  }

  function openSidebar() {
    els.sidebar.classList.add("open");
    els.scrim.hidden = false;
  }

  function closeSidebar() {
    els.sidebar.classList.remove("open");
    els.scrim.hidden = true;
  }

  function autoResize() {
    els.input.style.height = "auto";
    els.input.style.height = `${Math.min(els.input.scrollHeight, 200)}px`;
  }

  // ================= Events =================
  els.startBtn.addEventListener("click", () => go("#/new"));
  els.homeBtn.addEventListener("click", () => go("#/"));
  els.newChatBtn.addEventListener("click", () => go("#/new"));
  els.openSidebarBtn.addEventListener("click", openSidebar);
  els.closeSidebarBtn.addEventListener("click", closeSidebar);
  els.scrim.addEventListener("click", closeSidebar);

  els.clearAllBtn.addEventListener("click", () => {
    if (busy || !chats.length || !confirm("Delete all saved trips?")) return;
    chats = [];
    saveChats();
    renderRecent();
  });

  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (busy) return;
    const text = els.input.value;
    els.input.value = "";
    autoResize();
    send(text);
  });

  els.input.addEventListener("input", autoResize);
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { // Enter sends, Shift+Enter = new line
      e.preventDefault();
      els.form.requestSubmit();
    }
  });

  els.suggestions.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) send(chip.dataset.prompt);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSidebar();
  });

  window.addEventListener("hashchange", route);
  route();
})();
