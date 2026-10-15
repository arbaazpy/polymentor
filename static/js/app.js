/* PolyMentor front end: streams a turn over SSE and renders it.
   Saved turns (permalinks) reuse the same renderer. No build step. */
(function () {
  const LANE_NAMES = {
    dsa: "Algorithms", sysdes: "System design", behav: "Behavioral",
    resume: "Resume", mock: "Mock interviewer",
  };

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function md(s) {
    let h = esc(s);
    h = h.replace(/```[a-z]*\n?([\s\S]*?)```/g, '<pre class="bg-slate-950 rounded p-2 my-2 overflow-x-auto text-xs">$1</pre>');
    h = h.replace(/`([^`\n]+)`/g, '<code class="bg-slate-800 rounded px-1">$1</code>');
    h = h.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/^#{1,4}\s+(.+)$/gm, '<div class="font-semibold mt-2">$1</div>');
    h = h.replace(/^\s*(?:[-*]|\d+\.)\s+(.+)$/gm, '<div class="pl-4 -indent-3">• $1</div>');
    return h.replace(/\n{2,}/g, '<div class="h-2"></div>').replace(/\n/g, "<br>");
  }

  function confBadge(c) {
    if (c === null || c === undefined) return '<span class="text-slate-500">conf n/a</span>';
    const cls = c >= 0.8 ? "text-emerald-300" : c >= 0.5 ? "text-amber-300" : "text-rose-300";
    return `<span class="${cls}" title="Nugen confidence frames (weakly calibrated, see EVALUATION.md)">conf ${c.toFixed(2)}</span>`;
  }

  function csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  /* ---------- renderer ---------- */
  function Renderer(root, turnId) {
    this.root = root;
    this.turnId = turnId;
    root.innerHTML = "";
    this.routeBox = root.appendChild(el('<div class="mb-4"></div>'));
    this.notes = root.appendChild(el('<div class="space-y-2 mb-4"></div>'));
    this.cards = root.appendChild(el('<div class="grid gap-3 md:grid-cols-2"></div>'));
    this.recon = root.appendChild(el('<div class="mt-4 space-y-2"></div>'));
    this.synth = null;
    this.synthText = "";
    this.cardEls = {};
  }

  Renderer.prototype.route = function (r) {
    const lanes = r.lanes.map((l) => `<span class="font-mono text-indigo-300">expert.${esc(l)}</span>`).join(" · ");
    this.routeBox.innerHTML = `
      <div class="text-sm rounded-lg border border-slate-800 bg-slate-900/60 p-3">
        <div><span class="text-slate-400">Router →</span> ${lanes}
          <span class="text-xs text-slate-500 ml-2">${r.collaborative ? "split across lanes" : "single lane"} · ${esc(r.method)}</span></div>
        ${r.rationale ? `<div class="text-xs text-slate-500 mt-1">why: ${esc(r.rationale)}</div>` : ""}
      </div>`;
  };

  Renderer.prototype.pending = function (lane) {
    const card = el(`<div class="rounded-lg border border-slate-800 bg-slate-900/40 p-4 text-sm animate-pulse">
      <div class="font-medium">${esc(LANE_NAMES[lane] || lane)}</div>
      <div class="text-slate-500 text-xs mt-1">expert.${esc(lane)} is thinking…</div></div>`);
    this.cards.appendChild(card);
    this.cardEls[lane] = card;
  };

  Renderer.prototype.expert = function (e) {
    const statusTag = {
      answered: "", delegated: '<span class="text-xs text-amber-300 ml-2">handed off</span>',
      abstained: '<span class="text-xs text-amber-300 ml-2">not covered</span>',
      error: '<span class="text-xs text-rose-300 ml-2">error</span>',
    }[e.status] || "";
    const sources = (e.sections || []).map((s) => `<span class="font-mono">${esc(s)}</span>`).join("<br>");
    const claims = (e.claims || []).map((c) => `<div><span class="font-mono text-indigo-300">${esc(c.id)}</span> ${esc(c.text)}</div>`).join("");
    const body = e.status === "error" ? `<div class="text-rose-300">${esc(e.error)}</div>` : md(e.text);
    const card = el(`<div class="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-sm">
      <div class="flex items-baseline justify-between gap-2">
        <div><span class="font-medium">${esc(e.lane_name || LANE_NAMES[e.lane] || e.lane)}</span>${statusTag}</div>
        <div class="text-xs text-slate-400 whitespace-nowrap">v${esc(e.version)} · ${e.aligned ? "aligned" : "base"} · ${confBadge(e.confidence)}</div>
      </div>
      <div class="mt-2 leading-relaxed text-slate-200">${body}</div>
      <details class="mt-3 text-xs text-slate-400"><summary class="cursor-pointer">Raw expert output &amp; sources</summary>
        <div class="mt-2"><span class="text-slate-500">model</span> <span class="font-mono">${esc(e.model)}</span>${e.latency_ms ? ` · ${e.latency_ms} ms` : ""}</div>
        ${claims ? `<div class="mt-2"><div class="text-slate-500">claims</div>${claims}</div>` : ""}
        ${sources ? `<div class="mt-2"><div class="text-slate-500">grounded on</div>${sources}</div>` : ""}
        <pre class="mt-2 whitespace-pre-wrap bg-slate-950 rounded p-2">${esc(e.raw || e.text)}</pre>
      </details>
      <div class="fb mt-3 flex gap-2 text-xs" data-expert="${esc(e.lane)}"></div>
    </div>`);
    const old = this.cardEls[e.lane];
    if (old && e.status !== "delegated") old.replaceWith(card);
    else if (old) { old.replaceWith(card); delete this.cardEls[e.lane]; }
    else this.cards.appendChild(card);
    if (e.status !== "delegated") this.cardEls[e.lane] = card;
    if (this.turnId) this.feedbackButtons(card.querySelector(".fb"));
  };

  Renderer.prototype.delegation = function (d) {
    const verdict = d.honoured ? "honoured" : "vetoed";
    const cls = d.honoured ? "border-indigo-800" : "border-amber-700";
    this.notes.appendChild(el(`<div class="text-xs rounded border ${cls} bg-slate-900/60 p-2">
      expert.${esc(d.from)} tried to hand off to expert.${esc(d.to)}: <strong>${verdict}</strong> by the router (${esc(d.reason)})</div>`));
  };

  Renderer.prototype.reconciliation = function (notes) {
    for (const n of notes || []) {
      const cands = n.candidates.map((c) => `<div><span class="font-mono">${esc(c.lane)}</span> said: ${esc(c.text)}</div>`).join("");
      const tone = n.agreed ? "border-emerald-800 bg-emerald-950/20" : "border-amber-700 bg-amber-950/30";
      const head = n.agreed ? "✓ Lanes agree on" : "⚠ Reconciled";
      const ruling = n.agreed ? "" : (n.winner ? `, so <strong>${esc(n.winner)}</strong> wins` : "");
      this.recon.appendChild(el(`<div class="rounded-lg border ${tone} p-3 text-sm">
        <div class="font-medium ${n.agreed ? "text-emerald-200" : "text-amber-200"}">${head} <span class="font-mono">${esc(n.claim_id)}</span></div>
        <div class="text-xs mt-1 text-slate-300">${cands}</div>
        <div class="text-xs mt-1 text-slate-400">Rule: ${esc(n.rule)}${ruling}</div></div>`));
    }
  };

  Renderer.prototype.delta = function (text) {
    if (!this.synth) {
      const box = el(`<div class="mt-4 rounded-lg border border-indigo-800 bg-indigo-950/30 p-4 text-sm">
        <div class="font-medium text-indigo-200 mb-2">Combined plan <span class="text-xs text-slate-400">(coordinator model)</span></div>
        <div class="body leading-relaxed"></div><div class="fb mt-3 flex gap-2 text-xs" data-expert=""></div></div>`);
      this.root.insertBefore(box, this.recon.nextSibling);
      this.synth = box;
    }
    this.synthText += text;
    this.synth.querySelector(".body").innerHTML = md(this.synthText);
  };

  Renderer.prototype.done = function (d) {
    this.turnId = d.turn_id;
    this.root.querySelectorAll(".fb").forEach((b) => this.feedbackButtons(b));
    this.root.appendChild(el(`<div class="mt-4 text-xs text-slate-500">Saved · <a class="text-indigo-300 underline" href="${esc(d.url)}">permalink</a></div>`));
  };

  Renderer.prototype.error = function (msg) {
    this.root.appendChild(el(`<div class="mt-4 rounded border border-rose-800 bg-rose-950/40 p-3 text-sm text-rose-200">${esc(msg)}</div>`));
  };

  Renderer.prototype.feedbackButtons = function (box) {
    if (!box || box.dataset.ready) return;
    box.dataset.ready = "1";
    const expert = box.dataset.expert;
    box.innerHTML = `<button data-r="1" class="rounded border border-slate-700 px-2 py-0.5 hover:border-emerald-500">👍 helpful</button>
      <button data-r="-1" class="rounded border border-slate-700 px-2 py-0.5 hover:border-rose-500">👎 fix this</button>`;
    box.addEventListener("click", async (ev) => {
      const r = ev.target.dataset && ev.target.dataset.r;
      if (!r) return;
      let correction = "";
      if (r === "-1") correction = window.prompt("What should the answer have said? (optional, feeds the learning loop)") || "";
      const res = await fetch(`/v1/turns/${this.turnId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ rating: Number(r), expert, correction }),
      });
      box.innerHTML = res.ok ? '<span class="text-slate-400">Thanks, recorded for the learning loop.</span>'
        : '<span class="text-rose-300">Could not record feedback.</span>';
    });
  };

  Renderer.prototype.handle = function (ev) {
    switch (ev.type) {
      case "route": return this.route(ev);
      case "expert_start": return this.pending(ev.lane);
      case "expert": return this.expert(ev);
      case "delegation": return this.delegation(ev);
      case "reconciliation": return this.reconciliation(ev.notes);
      case "delta": return this.delta(ev.text);
      case "done": return this.done(ev);
      case "error": return this.error(ev.error);
    }
  };

  /* ---------- entry points ---------- */
  async function ask(prompt, root, btn) {
    btn.disabled = true;
    const view = new Renderer(root, null);
    try {
      const res = await fetch("/v1/turns/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ prompt }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({ error: res.statusText }));
        view.error(j.error || "Request failed");
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, i).trim();
          buf = buf.slice(i + 2);
          if (!frame.startsWith("data:")) continue;
          const data = frame.slice(5).trim();
          if (data && data !== "[DONE]") view.handle(JSON.parse(data));
        }
      }
    } catch (err) {
      view.error(`Connection lost: ${err}`);
    } finally {
      btn.disabled = false;
    }
  }

  window.PolyMentor = {
    initAsk() {
      const form = document.getElementById("ask-form");
      const input = document.getElementById("prompt");
      const btn = document.getElementById("ask-btn");
      const root = document.getElementById("result");
      document.querySelectorAll(".try").forEach((b) => b.addEventListener("click", () => { input.value = b.dataset.try; input.focus(); }));
      form.addEventListener("submit", (e) => { e.preventDefault(); if (input.value.trim()) ask(input.value.trim(), root, btn); });
    },
    renderSaved(t) {
      const view = new Renderer(document.getElementById("result"), t.id);
      view.route(t.route);
      (t.delegations || []).forEach((d) => view.delegation(d));
      (t.experts || []).forEach((e) => view.expert(e));
      view.reconciliation(t.reconciliation);
      if (t.synthesis) view.delta(t.synthesis);
      view.root.querySelectorAll(".fb").forEach((b) => view.feedbackButtons(b));
    },
  };
})();
