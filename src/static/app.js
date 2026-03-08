/* ===== Session Buddy — Client JS ===== */

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function toast(msg, type) {
  type = type || "info";
  var el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.className = "toast toast-" + type;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(function() { el.classList.add("hidden"); }, 3000);
}

async function api(url, opts) {
  opts = opts || {};
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (opts.body && typeof opts.body === "object") opts.body = JSON.stringify(opts.body);
  var res = await fetch(url, opts);
  var data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

// ---------------------------------------------------------------------------
// Auth form handlers
// ---------------------------------------------------------------------------

function initAuthForms() {
  var regForm = document.getElementById("registerForm");
  if (regForm) {
    regForm.addEventListener("submit", async function(e) {
      e.preventDefault();
      try {
        await api("/api/register", {
          method: "POST",
          body: {
            name: document.getElementById("name").value,
            email: document.getElementById("email").value,
            password: document.getElementById("password").value,
            school: document.getElementById("school").value,
          },
        });
        window.location.href = "/";
      } catch (err) {
        document.getElementById("authMsg").textContent = err.message;
      }
    });
  }

  var loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async function(e) {
      e.preventDefault();
      try {
        await api("/api/login", {
          method: "POST",
          body: {
            email: document.getElementById("email").value,
            password: document.getElementById("password").value,
          },
        });
        window.location.href = "/";
      } catch (err) {
        document.getElementById("authMsg").textContent = err.message;
      }
    });
  }

  var poForm = document.getElementById("poLoginForm");
  if (poForm) {
    poForm.addEventListener("submit", async function(e) {
      e.preventDefault();
      try {
        await api("/api/po/login", {
          method: "POST",
          body: { pin: document.getElementById("pin").value },
        });
        window.location.href = "/po";
      } catch (err) {
        document.getElementById("authMsg").textContent = err.message;
      }
    });
  }
}

// ---------------------------------------------------------------------------
// Logout
// ---------------------------------------------------------------------------

function initLogout() {
  var btn = document.getElementById("logoutBtn");
  if (btn) {
    btn.addEventListener("click", async function(e) {
      e.preventDefault();
      await fetch("/api/logout", { method: "POST" });
      window.location.href = "/login";
    });
  }
  var poBtn = document.getElementById("poLogoutBtn");
  if (poBtn) {
    poBtn.addEventListener("click", async function(e) {
      e.preventDefault();
      await fetch("/api/po/logout", { method: "POST" });
      window.location.href = "/";
    });
  }
}

// ---------------------------------------------------------------------------
// Speaker dashboard (index.html)
// ---------------------------------------------------------------------------

var pollTimer = null;

function initSpeakerDashboard() {
  var el = document.getElementById("speakerDashboard");
  if (!el) return;
  pollState();
  pollTimer = setInterval(pollState, 2000);
}

async function pollState() {
  try {
    var data = await api("/api/session/state");
    renderSpeakerView(data);
  } catch (e) {
    // silently retry on next interval
  }
}

function renderSpeakerView(s) {
  var el = document.getElementById("speakerDashboard");
  if (!el) return;

  if (s.phase === "idle" || !s.active_legislation) {
    el.innerHTML =
      '<div class="card text-center p-10">' +
        '<div class="w-16 h-16 bg-sb-navy/10 rounded-full flex items-center justify-center mx-auto mb-4">' +
          '<svg class="w-8 h-8 text-sb-navy/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>' +
        '</div>' +
        '<h2 class="text-xl font-bold section-title mb-2">Waiting for Debate</h2>' +
        '<p class="text-gray-400">The Presiding Officer has not opened debate on any legislation yet.</p>' +
      '</div>';
    return;
  }

  var leg = s.active_legislation;
  var side = s.next_side ? "Affirmative" : "Negative";
  var sideColor = s.next_side ? "text-green-700" : "text-sb-red";

  var speechLabel = "";
  if (s.speeches.length === 0) speechLabel = "(Authorship/Sponsorship)";
  else if (s.speeches.length === 1) speechLabel = "(First Negative)";

  // Speech history
  var historyHtml = "";
  if (s.speeches.length) {
    historyHtml = '<div class="card p-4 mb-4"><h3 class="font-bold text-sb-navy mb-2 text-sm uppercase tracking-wide">Speech History</h3><ol class="list-decimal ml-5 text-sm space-y-1">';
    for (var i = 0; i < s.speeches.length; i++) {
      var sp = s.speeches[i];
      var tag = sp.is_affirmative ? '<span class="text-green-700 font-bold">AFF</span>' : '<span class="text-sb-red font-bold">NEG</span>';
      historyHtml += '<li class="text-gray-600">' + sp.full_name + ' <span class="text-gray-400">(' + sp.school + ')</span> &mdash; ' + tag + ' <span class="text-gray-400">[' + sp.speech_type + ']</span></li>';
    }
    historyHtml += '</ol></div>';
  }

  // Current speech / questioning
  var currentHtml = "";
  if (s.phase === "speech_in_progress" && s.current_speech) {
    var cs = s.current_speech;
    var ctag = cs.is_affirmative ? "AFF" : "NEG";
    var ctagColor = cs.is_affirmative ? "text-green-700" : "text-sb-red";
    currentHtml =
      '<div class="card phase-card-speaking mb-4 p-5">' +
        '<div class="flex items-center gap-2 mb-2"><span class="w-2 h-2 bg-sb-gold rounded-full animate-pulse"></span><h3 class="font-bold text-sb-navy text-sm uppercase tracking-wide">Speech In Progress</h3></div>' +
        '<p class="text-lg font-semibold">' + cs.full_name + ' <span class="text-gray-400 font-normal">(' + cs.school + ')</span> &mdash; <span class="' + ctagColor + ' font-bold">' + ctag + '</span></p>' +
      '</div>';
  } else if (s.phase === "questioning" && s.current_speech) {
    var cs2 = s.current_speech;
    currentHtml =
      '<div class="card phase-card-question mb-4 p-5">' +
        '<div class="flex items-center gap-2 mb-2"><span class="w-2 h-2 bg-sb-navy rounded-full animate-pulse"></span><h3 class="font-bold text-sb-navy text-sm uppercase tracking-wide">Questioning Period</h3></div>' +
        '<p class="mb-3">Questions for: <strong>' + cs2.full_name + '</strong> (' + cs2.school + ')</p>' +
        '<button onclick="requestToQuestion()" class="btn btn-primary">Raise Hand to Question</button>' +
      '</div>';
    if (s.question_queue.length) {
      currentHtml += '<div class="card p-4 mb-4"><h4 class="font-bold text-sb-navy text-sm uppercase tracking-wide mb-2">Question Queue</h4><ol class="list-decimal ml-5 text-sm space-y-1">';
      for (var j = 0; j < s.question_queue.length; j++) {
        var q = s.question_queue[j];
        var st = q.status === "asking" ? ' <span class="badge badge-yellow">ASKING NOW</span>' : "";
        currentHtml += '<li class="text-gray-600">' + q.full_name + ' <span class="text-gray-400">(' + q.school + ')</span>' + st + '</li>';
      }
      currentHtml += '</ol></div>';
    }
  }

  // Speech queue
  var queueHtml = "";
  if (s.speech_queue.length) {
    queueHtml = '<div class="card p-4 mb-4"><h3 class="font-bold text-sb-navy mb-2 text-sm uppercase tracking-wide">Speech Queue</h3><div class="space-y-1">';
    for (var k = 0; k < s.speech_queue.length; k++) {
      var sq = s.speech_queue[k];
      var qtag = sq.is_affirmative ? '<span class="text-green-700 font-bold">AFF</span>' : '<span class="text-sb-red font-bold">NEG</span>';
      queueHtml += '<div class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-gray-50 text-sm"><span class="text-gray-400 font-mono text-xs">' + (k+1) + '.</span> ' + sq.full_name + ' <span class="text-gray-400">(' + sq.school + ')</span> &mdash; ' + qtag + ' <span class="text-gray-400">[' + sq.total_speeches + ' speeches]</span></div>';
    }
    queueHtml += '</div></div>';
  }

  // Request to speak buttons
  var actionHtml = "";
  if (s.phase === "speech_queue" || s.phase === "speech_in_progress") {
    actionHtml =
      '<div class="card p-4 mb-4"><h3 class="font-bold text-sb-navy mb-3 text-sm uppercase tracking-wide">Raise Your Hand</h3><div class="flex flex-wrap gap-2">' +
        '<button onclick="requestToSpeak(true)" class="btn btn-green">&#9757; Speak Affirmative</button>' +
        '<button onclick="requestToSpeak(false)" class="btn btn-red">&#9757; Speak Negative</button>' +
        '<button onclick="cancelSpeechRequest()" class="btn btn-gray">Cancel Request</button>' +
      '</div></div>';
  }

  el.innerHTML =
    '<div class="card mb-4 p-5 border-l-4" style="border-left-color:var(--sb-navy)">' +
      '<h2 class="text-xl font-extrabold text-sb-navy mb-1">' + leg.title + '</h2>' +
      '<p class="text-sm text-gray-400 mb-2">Authored by: ' + leg.school + '</p>' +
      (leg.body ? '<p class="text-sm text-gray-600 mb-3">' + leg.body + '</p>' : '') +
      '<p class="font-semibold text-sm">Next speech needed: <span class="' + sideColor + ' font-bold text-base">' + side + '</span> ' + speechLabel + '</p>' +
    '</div>' +
    currentHtml +
    actionHtml +
    queueHtml +
    historyHtml;
}

async function requestToSpeak(isAff) {
  try {
    await api("/api/speech/request", { method: "POST", body: { is_affirmative: isAff } });
    toast("Added to speech queue", "success");
    pollState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function cancelSpeechRequest() {
  try {
    await api("/api/speech/cancel", { method: "POST" });
    toast("Removed from queue", "success");
    pollState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function requestToQuestion() {
  try {
    await api("/api/question/request", { method: "POST" });
    toast("Added to question queue", "success");
    pollState();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// PO dashboard (po.html)
// ---------------------------------------------------------------------------

function initPODashboard() {
  var el = document.getElementById("poDashboard");
  if (!el) return;
  loadLegislation();
  pollPOState();
  pollTimer = setInterval(pollPOState, 2000);

  var addForm = document.getElementById("addLegForm");
  if (addForm) {
    addForm.addEventListener("submit", async function(e) {
      e.preventDefault();
      try {
        await api("/api/legislation", {
          method: "POST",
          body: {
            title: document.getElementById("legTitle").value,
            school: document.getElementById("legSchool").value,
            body: document.getElementById("legBody").value,
          },
        });
        addForm.reset();
        toast("Legislation added", "success");
        loadLegislation();
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }
}

async function loadLegislation() {
  var el = document.getElementById("legList");
  if (!el) return;
  try {
    var data = await api("/api/legislation");
    if (!data.legislation.length) {
      el.innerHTML = '<p class="text-gray-400 text-sm">No legislation added yet.</p>';
      return;
    }
    var html = "";
    for (var i = 0; i < data.legislation.length; i++) {
      var l = data.legislation[i];
      var statusBadge = l.status === "completed"
        ? '<span class="badge badge-gray">Done</span>'
        : l.status === "active"
        ? '<span class="badge badge-green">Active</span>'
        : '<span class="badge badge-blue">Pending</span>';
      var borderColor = l.status === "active" ? 'border-left-color:#16a34a' : l.status === "completed" ? 'border-left-color:var(--sb-gray-400)' : 'border-left-color:var(--sb-navy)';
      html +=
        '<div class="card p-3 mb-2 flex items-center justify-between border-l-4" style="' + borderColor + '">' +
          '<div>' +
            '<span class="font-bold text-sb-navy">' + l.leg_order + '.</span> ' +
            '<span class="font-semibold">' + l.title + '</span>' +
            ' <span class="text-xs text-gray-400">(' + l.school + ')</span> ' +
            statusBadge +
          '</div>' +
          '<div class="flex gap-1">' +
            (l.status === "pending" ? '<button onclick="openDebate(' + l.id + ')" class="btn btn-sm btn-green">Open</button>' : '') +
            (l.status === "pending" ? '<button onclick="deleteLeg(' + l.id + ')" class="btn btn-sm btn-red">Del</button>' : '') +
            (l.status === "pending" ? '<button onclick="moveLeg(' + l.id + ', -1)" class="btn btn-sm btn-gray">&#9650;</button><button onclick="moveLeg(' + l.id + ', 1)" class="btn btn-sm btn-gray">&#9660;</button>' : '') +
          '</div>' +
        '</div>';
    }
    el.innerHTML = html;
  } catch (err) {
    el.innerHTML = '<p class="text-red-500">' + err.message + '</p>';
  }
}

async function moveLeg(id, dir) {
  try {
    var data = await api("/api/legislation");
    var legs = data.legislation;
    var idx = -1;
    for (var i = 0; i < legs.length; i++) {
      if (legs[i].id === id) { idx = i; break; }
    }
    if (idx < 0) return;
    var newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= legs.length) return;
    var tmp = legs[idx];
    legs[idx] = legs[newIdx];
    legs[newIdx] = tmp;
    var order = [];
    for (var j = 0; j < legs.length; j++) order.push(legs[j].id);
    await api("/api/legislation/reorder", { method: "POST", body: { order: order } });
    loadLegislation();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function deleteLeg(id) {
  if (!confirm("Delete this legislation?")) return;
  try {
    await api("/api/legislation/" + id, { method: "DELETE" });
    toast("Deleted", "success");
    loadLegislation();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function openDebate(legId) {
  try {
    await api("/api/session/open-debate", { method: "POST", body: { legislation_id: legId } });
    toast("Debate opened", "success");
    loadLegislation();
    pollPOState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function closeDebate() {
  try {
    await api("/api/session/close-debate", { method: "POST" });
    toast("Debate closed", "success");
    loadLegislation();
    pollPOState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function resetSession() {
  if (!confirm("Reset the entire session? This clears all speeches and queues.")) return;
  try {
    await api("/api/session/reset", { method: "POST" });
    toast("Session reset", "success");
    loadLegislation();
    pollPOState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function pollPOState() {
  try {
    var data = await api("/api/session/state");
    renderPODebatePanel(data);
  } catch (e) {
    // retry next interval
  }
}

function renderPODebatePanel(s) {
  var el = document.getElementById("debatePanel");
  if (!el) return;

  if (s.phase === "idle" || !s.active_legislation) {
    el.innerHTML = '<div class="text-center py-8"><div class="w-12 h-12 bg-sb-navy/10 rounded-full flex items-center justify-center mx-auto mb-3"><svg class="w-6 h-6 text-sb-navy/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/></svg></div><p class="text-gray-400">No legislation is currently being debated.<br>Open debate on a legislation item above.</p></div>';
    return;
  }

  var leg = s.active_legislation;
  var side = s.next_side ? "Affirmative" : "Negative";
  var sideColor = s.next_side ? "text-green-700" : "text-sb-red";

  var speechLabel = "";
  if (s.speeches.length === 0) speechLabel = "(Authorship/Sponsorship)";
  else if (s.speeches.length === 1) speechLabel = "(First Negative)";

  // History
  var historyHtml = "";
  if (s.speeches.length) {
    historyHtml = '<h4 class="font-bold text-sb-navy text-sm uppercase tracking-wide mt-4 mb-2">Speech History</h4><ol class="list-decimal ml-5 text-sm space-y-1">';
    for (var i = 0; i < s.speeches.length; i++) {
      var sp = s.speeches[i];
      var tag = sp.is_affirmative ? '<span class="text-green-700 font-bold">AFF</span>' : '<span class="text-sb-red font-bold">NEG</span>';
      historyHtml += '<li class="text-gray-600">' + sp.full_name + ' <span class="text-gray-400">(' + sp.school + ')</span> &mdash; ' + tag + ' <span class="text-gray-400">[' + sp.speech_type + ']</span></li>';
    }
    historyHtml += '</ol>';
  }

  // Current speech
  var currentHtml = "";
  if (s.phase === "speech_in_progress" && s.current_speech) {
    var cs = s.current_speech;
    var ctag = cs.is_affirmative ? "AFF" : "NEG";
    var ctagColor = cs.is_affirmative ? "text-green-700" : "text-sb-red";
    currentHtml =
      '<div class="card phase-card-speaking p-4 mb-3">' +
        '<div class="flex items-center gap-2 mb-2"><span class="w-2 h-2 bg-sb-gold rounded-full animate-pulse"></span><h4 class="font-bold text-sb-navy text-sm uppercase tracking-wide">Currently Speaking</h4></div>' +
        '<p class="text-lg font-semibold">' + cs.full_name + ' <span class="text-gray-400 font-normal">(' + cs.school + ')</span> &mdash; <span class="' + ctagColor + ' font-bold">' + ctag + '</span> <span class="text-gray-400">[' + cs.speech_type + ']</span></p>' +
        '<button onclick="completeSpeech()" class="btn btn-primary mt-3">Speech Done &rarr; Questioning</button>' +
      '</div>';
  } else if (s.phase === "questioning" && s.current_speech) {
    var cs2 = s.current_speech;
    currentHtml =
      '<div class="card phase-card-question p-4 mb-3">' +
        '<div class="flex items-center gap-2 mb-2"><span class="w-2 h-2 bg-sb-navy rounded-full animate-pulse"></span><h4 class="font-bold text-sb-navy text-sm uppercase tracking-wide">Questioning: ' + cs2.full_name + '</h4></div>';
    if (s.question_queue.length) {
      currentHtml += '<ul class="text-sm mt-2 space-y-1">';
      for (var j = 0; j < s.question_queue.length; j++) {
        var q = s.question_queue[j];
        if (q.status === "asking") {
          currentHtml += '<li class="flex items-center gap-2"><span class="badge badge-yellow">ASKING</span><strong>' + q.full_name + '</strong> (' + q.school + ') ' +
            '<button onclick="doneQuestion(' + q.id + ')" class="btn btn-sm btn-gray ml-auto">Done</button></li>';
        } else {
          currentHtml += '<li class="flex items-center gap-2">' + q.full_name + ' <span class="text-gray-400">(' + q.school + ')</span> ' +
            '<button onclick="selectQuestioner(' + q.id + ')" class="btn btn-sm btn-primary ml-auto">Select</button></li>';
        }
      }
      currentHtml += '</ul>';
    } else {
      currentHtml += '<p class="text-sm text-gray-400 mt-1">No questioners yet.</p>';
    }
    currentHtml += '<button onclick="endQuestioning()" class="btn btn-gray mt-3">End Questioning &rarr; Next Speech</button></div>';
  }

  // Speech queue with recommendation
  var queueHtml = "";
  if (s.phase === "speech_queue") {
    if (s.speech_queue.length) {
      // Find recommended: first person whose side matches next_side
      var recommendedId = null;
      for (var k = 0; k < s.speech_queue.length; k++) {
        if (s.speech_queue[k].is_affirmative === s.next_side) {
          recommendedId = s.speech_queue[k].id;
          break;
        }
      }
      queueHtml = '<h4 class="font-bold text-sb-navy text-sm uppercase tracking-wide mb-2">Speech Queue <span class="font-normal normal-case text-gray-400">(sorted by precedence)</span></h4>';
      queueHtml += '<div class="space-y-2">';
      for (var m = 0; m < s.speech_queue.length; m++) {
        var sq = s.speech_queue[m];
        var sqtag = sq.is_affirmative ? '<span class="text-green-700 font-bold">AFF</span>' : '<span class="text-sb-red font-bold">NEG</span>';
        var rec = sq.id === recommendedId ? '<span class="badge badge-yellow">RECOMMENDED</span>' : "";
        var recClass = sq.id === recommendedId ? 'phase-card-speaking' : '';
        queueHtml +=
          '<div class="card p-3 flex items-center justify-between ' + recClass + '">' +
            '<span class="text-sm">' + sq.full_name + ' <span class="text-gray-400">(' + sq.school + ')</span> &mdash; ' + sqtag + ' <span class="text-gray-400">[' + sq.total_speeches + ' speeches]</span> ' + rec + '</span>' +
            '<button onclick="selectSpeaker(' + sq.id + ')" class="btn btn-sm btn-green">Select</button>' +
          '</div>';
      }
      queueHtml += '</div>';
    } else {
      queueHtml = '<p class="text-sm text-gray-400">No speakers in queue. Waiting for speakers to raise their hands...</p>';
    }
  }

  el.innerHTML =
    '<div class="card p-5 mb-4 border-l-4" style="border-left-color:var(--sb-navy)">' +
      '<div class="flex justify-between items-start">' +
        '<div>' +
          '<h3 class="text-lg font-extrabold text-sb-navy">' + leg.title + '</h3>' +
          '<p class="text-sm text-gray-400">' + leg.school + '</p>' +
          (leg.body ? '<p class="text-sm text-gray-600 mt-1">' + leg.body + '</p>' : '') +
        '</div>' +
        '<button onclick="closeDebate()" class="btn btn-sm btn-red uppercase tracking-wide">Close Debate</button>' +
      '</div>' +
      '<p class="mt-3 font-semibold text-sm">Next: <span class="' + sideColor + ' font-bold text-base">' + side + '</span> ' + speechLabel + '</p>' +
    '</div>' +
    currentHtml +
    queueHtml +
    historyHtml;
}

async function selectSpeaker(queueId) {
  try {
    await api("/api/speech/select/" + queueId, { method: "POST" });
    toast("Speaker selected", "success");
    pollPOState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function completeSpeech() {
  try {
    await api("/api/speech/complete", { method: "POST" });
    toast("Moved to questioning", "success");
    pollPOState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function endQuestioning() {
  try {
    await api("/api/speech/end-questioning", { method: "POST" });
    toast("Ready for next speech", "success");
    pollPOState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function selectQuestioner(queueId) {
  try {
    await api("/api/question/select/" + queueId, { method: "POST" });
    pollPOState();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function doneQuestion(queueId) {
  try {
    await api("/api/question/done/" + queueId, { method: "POST" });
    pollPOState();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", function() {
  initAuthForms();
  initLogout();
  initSpeakerDashboard();
  initPODashboard();
});
