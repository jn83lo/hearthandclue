/* Printable puzzle pages: anonymous counts, and the play-it-here grid.
   No cookie, no identifier: an event name goes to our own Netlify function,
   which keeps a plain per-day tally (see /privacy). */
(function () {
  "use strict";

  function track(name) {
    try {
      var payload = JSON.stringify({ name: name });
      var url = "/.netlify/functions/event";
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([payload], { type: "application/json" }));
      } else if (window.fetch) {
        fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, keepalive: true }).catch(function () {});
      }
    } catch (e) {}
  }

  track("print_view");
  try {
    if (/[?&]src=pin(&|$)/.test(location.search)) track("print_from_pin");
  } catch (e) {}

  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest("[data-ev]") : null;
    if (a) track(a.getAttribute("data-ev"));
  });

  /* ---------- boxes that change on a date ----------
     data-until="YYYY-MM-DD": shown up to and including that day.
     data-after="YYYY-MM-DD": shown from the day after. The date is the
     visitor's own. Without this script the first shows and the second
     stays hidden, which is right until the date. */
  try {
    var now = new Date();
    var today = now.getFullYear() + "-" + ("0" + (now.getMonth() + 1)).slice(-2) + "-" + ("0" + now.getDate()).slice(-2);
    var dated = document.querySelectorAll("[data-until], [data-after]");
    for (var k = 0; k < dated.length; k++) {
      var until = dated[k].getAttribute("data-until"), after = dated[k].getAttribute("data-after");
      if (until) dated[k].hidden = today > until;
      if (after) dated[k].hidden = !(today > after);
    }
  } catch (e) {}

  /* ---------- play it here ---------- */
  var dataEl = document.getElementById("puzzle-data");
  var root = document.getElementById("play");
  if (!dataEl || !root) return;

  var puzzle;
  try { puzzle = JSON.parse(dataEl.textContent); } catch (e) { return; }
  var N = puzzle.grid.length;
  var gridEl = root.querySelector(".grid");
  var statusEl = root.querySelector(".status");
  var listEl = root.querySelector(".wordlist");
  var wonEl = root.querySelector(".won");
  var liveEl = document.getElementById("live");
  var resetBtn = root.querySelector("[data-reset]");

  var found = {};        // word -> array of cell indexes
  var current = [];      // cells in the selection being made
  var anchor = null;     // first cell of a selection
  var armed = false;     // true after a single tap: the next tap ends the word
  var started = false;
  var done = false;

  function say(msg) { if (liveEl) liveEl.textContent = msg; }

  function letterAt(i) { return puzzle.grid[Math.floor(i / N)].charAt(i % N); }

  function pathBetween(a, b) {
    var ar = Math.floor(a / N), ac = a % N, br = Math.floor(b / N), bc = b % N;
    var dr = br - ar, dc = bc - ac;
    var steps = Math.max(Math.abs(dr), Math.abs(dc));
    if (steps === 0) return [a];
    if (!(dr === 0 || dc === 0 || Math.abs(dr) === Math.abs(dc))) return null;
    var sr = dr === 0 ? 0 : dr / Math.abs(dr), sc = dc === 0 ? 0 : dc / Math.abs(dc);
    var out = [];
    for (var k = 0; k <= steps; k++) out.push((ar + sr * k) * N + (ac + sc * k));
    return out;
  }

  function build() {
    var html = "";
    for (var i = 0; i < N * N; i++) {
      html += '<button class="cell" type="button" data-i="' + i + '" aria-label="Row ' + (Math.floor(i / N) + 1) +
              ", column " + (i % N + 1) + ", letter " + letterAt(i) + '">' + letterAt(i) + "</button>";
    }
    gridEl.className = "grid n" + N;
    gridEl.style.gridTemplateColumns = "repeat(" + N + ",1fr)";
    gridEl.innerHTML = html;
    var items = "";
    for (var w = 0; w < puzzle.words.length; w++) items += "<li>" + puzzle.words[w] + "</li>";
    listEl.innerHTML = items;
    paint();
  }

  function paint() {
    var inFound = {};
    for (var w in found) for (var k = 0; k < found[w].length; k++) inFound[found[w][k]] = true;
    var cells = gridEl.children;
    for (var i = 0; i < cells.length; i++) {
      var cls = "cell";
      if (inFound[i]) cls += " found";
      if (current.indexOf(i) !== -1) cls += " sel";
      if (armed && anchor === i) cls += " anchor";
      cells[i].className = cls;
    }
    var n = 0;
    var lis = listEl.children;
    for (var j = 0; j < lis.length; j++) {
      var isDone = !!found[lis[j].textContent];
      lis[j].className = isDone ? "done" : "";
      if (isDone) n++;
    }
    statusEl.textContent = "Found " + n + " of " + puzzle.words.length;
    if (resetBtn) resetBtn.disabled = n === 0;
  }

  function commit(cells) {
    var s = "";
    for (var k = 0; k < cells.length; k++) s += letterAt(cells[k]);
    var r = s.split("").reverse().join("");
    for (var w = 0; w < puzzle.words.length; w++) {
      var word = puzzle.words[w];
      if (!found[word] && (word === s || word === r)) {
        found[word] = cells.slice();
        say(word + " found.");
        if (Object.keys(found).length === puzzle.words.length) finish();
        return true;
      }
    }
    return false;
  }

  function finish() {
    done = true;
    wonEl.hidden = false;
    say("All words found.");
    track("print_solved");
  }

  function begin() { if (!started) { started = true; track("print_play"); } }

  function indexFromPoint(x, y) {
    var el = document.elementFromPoint(x, y);
    if (el && el.classList && el.classList.contains("cell")) return Number(el.getAttribute("data-i"));
    return null;
  }

  var dragging = false, moved = false;

  gridEl.addEventListener("pointerdown", function (e) {
    var i = indexFromPoint(e.clientX, e.clientY);
    if (i === null || done) return;
    e.preventDefault();
    try { gridEl.setPointerCapture(e.pointerId); } catch (err) {}
    begin();
    if (armed && anchor !== null) {
      // second tap of a tap-tap selection
      var p = pathBetween(anchor, i);
      armed = false;
      if (p && p.length > 1) { if (!commit(p)) say("Not one of the words."); }
      else if (!p) say("Words run in a straight line.");
      anchor = null; current = []; dragging = false;
      paint();
      return;
    }
    dragging = true; moved = false; anchor = i; current = [i];
    paint();
  });
  gridEl.addEventListener("pointermove", function (e) {
    if (!dragging) return;
    e.preventDefault();
    var i = indexFromPoint(e.clientX, e.clientY);
    if (i === null || anchor === null) return;
    var p = pathBetween(anchor, i);
    if (p) { if (p.length > 1) moved = true; current = p; paint(); }
  });
  function endDrag() {
    if (!dragging) return;
    dragging = false;
    if (!moved || current.length < 2) {
      // a single tap: keep the first letter and wait for a tap on the last
      armed = true; current = [];
      say("First letter chosen. Now tap the last letter.");
      paint();
      return;
    }
    commit(current);
    anchor = null; current = [];
    paint();
  }
  gridEl.addEventListener("pointerup", endDrag);
  gridEl.addEventListener("pointercancel", function () { dragging = false; armed = false; anchor = null; current = []; paint(); });

  // Keyboard: Enter on the first letter, then Enter on the last. Escape cancels.
  gridEl.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { armed = false; anchor = null; current = []; paint(); return; }
    if (e.key !== "Enter" && e.key !== " ") return;
    var el = document.activeElement;
    if (!el || !el.classList.contains("cell") || done) return;
    e.preventDefault();
    begin();
    var i = Number(el.getAttribute("data-i"));
    if (!armed || anchor === null) { armed = true; anchor = i; say("First letter chosen. Move to the last letter and press Enter."); }
    else {
      var p = pathBetween(anchor, i);
      armed = false; anchor = null;
      if (!p || p.length < 2) say("Words run in a straight line.");
      else if (!commit(p)) say("Not one of the words.");
    }
    paint();
  });

  if (resetBtn) resetBtn.addEventListener("click", function () {
    found = {}; current = []; anchor = null; armed = false; done = false;
    wonEl.hidden = true;
    say("Cleared.");
    paint();
  });

  build();
})();
