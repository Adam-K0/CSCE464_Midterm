/* ===== Congressional Debate — Client JS ===== */

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
      '<div class="card text-center p-8">' +
        '<h2 class="text-xl font-semibold mb-2">Waiting for Debate</h2>' +
        '<p class="text-gray-500">The Presiding Officer has not opened debate on any legislation yet.</p>' +
      '</div>';
    return;
  }

  var leg = s.active_legislation;
  var side = s.next_side ? "Affirmative" : "Negative";
  var sideColor = s.next_side ? "text-green-700" : "text-red-700";

  var speechLabel = "";
  if (s.speeches.length === 0) speechLabel = "(Authorship/Sponsorship)";
  else if (s.speeches.length === 1) speechLabel = "(First Negative)";

  // Speech history
  var historyHtml = "";
  if (s.speeches.length) {
    historyHtml = '<div class="mb-4"><h3 class="font-semibold mb-1">Speeches Given</h3><ol class="list-decimal ml-5 text-sm">';
    for (var i = 0; i < s.speeches.length; i++) {
      var sp = s.speeches[i];
      var tag = sp.is_affirmative ? '<span class="text-green-700">AFF</span>' : '<span class="text-red-700">NEG</span>';
      historyHtml += '<li>' + sp.full_name + ' (' + sp.school + ') &mdash; ' + tag + ' [' + sp.speech_type + ']</li>';
    }
    historyHtml += '</ol></div>';
  }

  // Current speech / questioning
  var currentHtml = "";
  if (s.phase === "speech_in_progress" && s.current_speech) {
    var cs = s.current_speech;
    var ctag = cs.is_affirmative ? "AFF" : "NEG";
    currentHtml =
      '<div class="card bg-yellow-50 border-yellow-300 mb-4 p-4">' +
        '<h3 class="font-semibold">Speech In Progress</h3>' +
        '<p class="text-lg">' + cs.full_name + ' (' + cs.school + ') &mdash; ' + ctag + '</p>' +
      '</div>';
  } else if (s.phase === "questioning" && s.current_speech) {
    var cs2 = s.current_speech;
    currentHtml =
      '<div class="card bg-blue-50 border-blue-300 mb-4 p-4">' +
        '<h3 class="font-semibold">Questioning Period</h3>' +
        '<p>Questions for: ' + cs2.full_name + ' (' + cs2.school + ')</p>' +
        '<button onclick="requestToQuestion()" class="btn btn-blue mt-2">Raise Hand to Question</button>' +
      '</div>';
    if (s.question_queue.length) {
      currentHtml += '<div class="mb-4"><h4 class="font-semibold text-sm">Question Queue</h4><ol class="list-decimal ml-5 text-sm">';
      for (var j = 0; j < s.question_queue.length; j++) {
        var q = s.question_queue[j];
        var st = q.status === "asking" ? " <strong>(asking now)</strong>" : "";
        currentHtml += '<li>' + q.full_name + ' (' + q.school + ')' + st + '</li>';
      }
      currentHtml += '</ol></div>';
    }
  }

  // Speech queue
  var queueHtml = "";
  if (s.speech_queue.length) {
    queueHtml = '<div class="mb-4"><h3 class="font-semibold mb-1">Speech Queue</h3><ol class="list-decimal ml-5 text-sm">';
    for (var k = 0; k < s.speech_queue.length; k++) {
      var sq = s.speech_queue[k];
      var qtag = sq.is_affirmative ? '<span class="text-green-700">AFF</span>' : '<span class="text-red-700">NEG</span>';
      queueHtml += '<li>' + sq.full_name + ' (' + sq.school + ') &mdash; ' + qtag + ' [speeches: ' + sq.total_speeches + ']</li>';
    }
    queueHtml += '</ol></div>';
  }

  // Request to speak buttons
  var actionHtml = "";
  if (s.phase === "speech_queue" || s.phase === "speech_in_progress") {
    actionHtml =
      '<div class="flex gap-2 mb-4">' +
        '<button onclick="requestToSpeak(true)" class="btn btn-green">Speak Affirmative</button>' +
        '<button onclick="requestToSpeak(false)" class="btn btn-red">Speak Negative</button>' +
        '<button onclick="cancelSpeechRequest()" class="btn btn-gray">Cancel Request</button>' +
      '</div>';
  }

  el.innerHTML =
    '<div class="card mb-4 p-4">' +
      '<h2 class="text-xl font-bold mb-1">' + leg.title + '</h2>' +
      '<p class="text-sm text-gray-500 mb-2">Authored by: ' + leg.school + '</p>' +
      (leg.body ? '<p class="text-sm mb-3">' + leg.body + '</p>' : '') +
      '<p class="font-semibold">Next speech needed: <span class="' + sideColor + '">' + side + '</span> ' + speechLabel + '</p>' +
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
      el.innerHTML = '<p class="text-gray-500 text-sm">No legislation added yet.</p>';
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
      html +=
        '<div class="card p-3 mb-2 flex items-center justify-between">' +
          '<div>' +
            '<span class="font-semibold">' + l.leg_order + '.</span> ' + l.title +
            ' <span class="text-xs text-gray-400">(' + l.school + ')</span> ' +
            statusBadge +
          '</div>' +
          '<div class="flex gap-1">' +
            (l.status === "pending" ? '<button onclick="openDebate(' + l.id + ')" class="btn btn-sm btn-green">Open Debate</button>' : '') +
            (l.status === "pending" ? '<button onclick="deleteLeg(' + l.id + ')" class="btn btn-sm btn-red">Delete</button>' : '') +
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
    el.innerHTML = '<p class="text-gray-500">No legislation is currently being debated. Open debate on a legislation item above.</p>';
    return;
  }

  var leg = s.active_legislation;
  var side = s.next_side ? "Affirmative" : "Negative";
  var sideColor = s.next_side ? "text-green-700" : "text-red-700";

  var speechLabel = "";
  if (s.speeches.length === 0) speechLabel = "(Authorship/Sponsorship)";
  else if (s.speeches.length === 1) speechLabel = "(First Negative)";

  // History
  var historyHtml = "";
  if (s.speeches.length) {
    historyHtml = '<h4 class="font-semibold text-sm mt-3 mb-1">Speech History</h4><ol class="list-decimal ml-5 text-sm">';
    for (var i = 0; i < s.speeches.length; i++) {
      var sp = s.speeches[i];
      var tag = sp.is_affirmative ? "AFF" : "NEG";
      historyHtml += '<li>' + sp.full_name + ' (' + sp.school + ') &mdash; ' + tag + ' [' + sp.speech_type + ']</li>';
    }
    historyHtml += '</ol>';
  }

  // Current speech
  var currentHtml = "";
  if (s.phase === "speech_in_progress" && s.current_speech) {
    var cs = s.current_speech;
    var ctag = cs.is_affirmative ? "AFF" : "NEG";
    currentHtml =
      '<div class="card bg-yellow-50 border-yellow-300 p-3 mb-3">' +
        '<h4 class="font-bold">Currently Speaking</h4>' +
        '<p class="text-lg">' + cs.full_name + ' (' + cs.school + ') &mdash; ' + ctag + ' [' + cs.speech_type + ']</p>' +
        '<button onclick="completeSpeech()" class="btn btn-blue mt-2">Speech Done &rarr; Questioning</button>' +
      '</div>';
  } else if (s.phase === "questioning" && s.current_speech) {
    var cs2 = s.current_speech;
    currentHtml =
      '<div class="card bg-blue-50 border-blue-300 p-3 mb-3">' +
        '<h4 class="font-bold">Questioning: ' + cs2.full_name + '</h4>';
    if (s.question_queue.length) {
      currentHtml += '<ul class="text-sm mt-2">';
      for (var j = 0; j < s.question_queue.length; j++) {
        var q = s.question_queue[j];
        if (q.status === "asking") {
          currentHtml += '<li><strong>' + q.full_name + ' (' + q.school + ')</strong> &mdash; asking now ' +
            '<button onclick="doneQuestion(' + q.id + ')" class="btn btn-sm btn-gray ml-1">Done</button></li>';
        } else {
          currentHtml += '<li>' + q.full_name + ' (' + q.school + ') ' +
            '<button onclick="selectQuestioner(' + q.id + ')" class="btn btn-sm btn-blue ml-1">Select</button></li>';
        }
      }
      currentHtml += '</ul>';
    } else {
      currentHtml += '<p class="text-sm text-gray-500 mt-1">No questioners yet.</p>';
    }
    currentHtml += '<button onclick="endQuestioning()" class="btn btn-gray mt-2">End Questioning &rarr; Next Speech</button></div>';
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
      queueHtml = '<h4 class="font-semibold text-sm mb-1">Speech Queue <span class="text-xs text-gray-400">(sorted by precedence/recency)</span></h4>';
      queueHtml += '<div class="space-y-1">';
      for (var m = 0; m < s.speech_queue.length; m++) {
        var sq = s.speech_queue[m];
        var sqtag = sq.is_affirmative ? '<span class="text-green-700 font-bold">AFF</span>' : '<span class="text-red-700 font-bold">NEG</span>';
        var rec = sq.id === recommendedId ? '<span class="badge badge-yellow">RECOMMENDED</span>' : "";
        queueHtml +=
          '<div class="card p-2 flex items-center justify-between ' + (sq.id === recommendedId ? 'bg-yellow-50 border-yellow-300' : '') + '">' +
            '<span>' + sq.full_name + ' (' + sq.school + ') &mdash; ' + sqtag + ' [speeches: ' + sq.total_speeches + '] ' + rec + '</span>' +
            '<button onclick="selectSpeaker(' + sq.id + ')" class="btn btn-sm btn-green">Select</button>' +
          '</div>';
      }
      queueHtml += '</div>';
    } else {
      queueHtml = '<p class="text-sm text-gray-500">No speakers in queue. Waiting for speakers to raise their hands...</p>';
    }
  }

  el.innerHTML =
    '<div class="card p-4 mb-3">' +
      '<div class="flex justify-between items-start">' +
        '<div>' +
          '<h3 class="text-lg font-bold">' + leg.title + '</h3>' +
          '<p class="text-sm text-gray-500">' + leg.school + '</p>' +
          (leg.body ? '<p class="text-sm mt-1">' + leg.body + '</p>' : '') +
        '</div>' +
        '<button onclick="closeDebate()" class="btn btn-sm btn-red">Close Debate</button>' +
      '</div>' +
      '<p class="mt-2 font-semibold">Next: <span class="' + sideColor + '">' + side + '</span> ' + speechLabel + '</p>' +
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
