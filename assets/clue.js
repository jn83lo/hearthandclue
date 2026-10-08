/* The Daily Clue: the word search game. Shared by the home page (today's
   puzzle, built from THEMES) and the /daily/<issue>/ pages (one past day,
   from window.DC_DAY). Moved here from Index.html unchanged apart from that. */
(function () {
  "use strict";

  var SIZE = 10;
  var EPOCH = Date.UTC(2026, 0, 1);
  var DIRS = [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,-1],[1,-1],[-1,1]];

  // The home page defines THEMES inline (scripts/engine.py reads it there).
  var THEMES = window.THEMES || [];
  // Set only on a /daily/<issue>/ page: that one day's puzzle, stored with the
  // page exactly as it was played, so a later change to THEMES cannot alter it.
  var DAY = window.DC_DAY || null;
  var ARCHIVE_FROM = 236; // the first day that has a page under /daily/

  /* ---------- deterministic randomness ---------- */

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* ---------- which puzzle is today's ---------- */

  function dayNumber(d) {
    return Math.floor((Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) - EPOCH) / 86400000);
  }

  var EVERGREEN = THEMES.filter(function (t) { return t.kind === "ever"; });

  function themeFor(d) {
    var m = d.getMonth() + 1, day = d.getDate(), i;
    for (i = 0; i < THEMES.length; i++) {
      var t = THEMES[i];
      if (t.kind === "dated" && t.months.indexOf(m) !== -1 && day >= t.days[0] && day <= t.days[1]) return t;
    }
    var season = null;
    for (i = 0; i < THEMES.length; i++) {
      if (THEMES[i].kind === "season" && THEMES[i].months.indexOf(m) !== -1) { season = THEMES[i]; break; }
    }
    var pool = season ? EVERGREEN.concat([season]) : EVERGREEN;
    var n = dayNumber(d);
    return pool[((n % pool.length) + pool.length) % pool.length];
  }

  /* ---------- grid construction ---------- */

  function place(grid, word, rng) {
    for (var attempt = 0; attempt < 400; attempt++) {
      var dir = DIRS[Math.floor(rng() * DIRS.length)];
      var sx = Math.floor(rng() * SIZE), sy = Math.floor(rng() * SIZE);
      var ok = true, i, x, y;
      for (i = 0; i < word.length; i++) {
        x = sx + dir[0] * i; y = sy + dir[1] * i;
        if (x < 0 || x >= SIZE || y < 0 || y >= SIZE) { ok = false; break; }
        var cur = grid[y][x];
        if (cur !== null && cur !== word.charAt(i)) { ok = false; break; }
      }
      if (!ok) continue;
      var cells = [];
      for (i = 0; i < word.length; i++) {
        x = sx + dir[0] * i; y = sy + dir[1] * i;
        grid[y][x] = word.charAt(i);
        cells.push(y * SIZE + x);
      }
      return cells;
    }
    return null;
  }

  function findable(grid, word) {
    for (var y = 0; y < SIZE; y++) for (var x = 0; x < SIZE; x++) {
      for (var d = 0; d < DIRS.length; d++) {
        var ok = true;
        for (var i = 0; i < word.length; i++) {
          var nx = x + DIRS[d][0] * i, ny = y + DIRS[d][1] * i;
          if (nx < 0 || nx >= SIZE || ny < 0 || ny >= SIZE || grid[ny][nx] !== word.charAt(i)) { ok = false; break; }
        }
        if (ok) return true;
      }
    }
    return false;
  }

  // A stored grid (a past day's page): find where each word sits.
  function locate(grid, word) {
    for (var y = 0; y < SIZE; y++) for (var x = 0; x < SIZE; x++) {
      for (var d = 0; d < DIRS.length; d++) {
        var cells = [];
        for (var i = 0; i < word.length; i++) {
          var nx = x + DIRS[d][0] * i, ny = y + DIRS[d][1] * i;
          if (nx < 0 || nx >= SIZE || ny < 0 || ny >= SIZE || grid[ny][nx] !== word.charAt(i)) { cells = null; break; }
          cells.push(ny * SIZE + nx);
        }
        if (cells) return cells;
      }
    }
    return null;
  }

  function fromGrid(rows, words) {
    if (!rows || rows.length !== SIZE) return null;
    var grid = [], spots = {}, i;
    for (i = 0; i < SIZE; i++) {
      if (String(rows[i]).length !== SIZE) return null;
      grid.push(String(rows[i]).split(""));
    }
    for (i = 0; i < words.length; i++) {
      var cells = locate(grid, words[i]);
      if (!cells) return null;
      spots[words[i]] = cells;
    }
    return { grid: grid, spots: spots };
  }

  // Same seed, same puzzle — everywhere, every time. Never returns an unsolvable grid.
  function buildPuzzle(words, seed) {
    var ordered = words.slice().sort(function (a, b) { return b.length - a.length; });
    for (var round = 0; round < 60; round++) {
      var rng = mulberry32(seed + round * 7919);
      var grid = [], y;
      for (y = 0; y < SIZE; y++) { grid.push(new Array(SIZE).fill(null)); }
      var spots = {}, failed = false;
      for (var i = 0; i < ordered.length; i++) {
        var cells = place(grid, ordered[i], rng);
        if (!cells) { failed = true; break; }
        spots[ordered[i]] = cells;
      }
      if (failed) continue;
      for (y = 0; y < SIZE; y++) for (var x = 0; x < SIZE; x++) {
        if (grid[y][x] === null) grid[y][x] = String.fromCharCode(65 + Math.floor(rng() * 26));
      }
      var allOk = words.every(function (w) { return findable(grid, w); });
      if (allOk) return { grid: grid, spots: spots };
    }
    return null;
  }

  /* ---------- state ---------- */

  var today, theme, puzzle, issueNo;
  if (DAY) {
    var ymd = String(DAY.date).split("-");
    today = new Date(+ymd[0], +ymd[1] - 1, +ymd[2], 12);
    theme = { title: DAY.title, note: DAY.note, subject: DAY.subject, url: DAY.url, cta: DAY.cta, words: DAY.words };
    puzzle = fromGrid(DAY.grid, DAY.words);
    issueNo = DAY.n;
  } else {
    today = new Date();
    theme = themeFor(today);
    var seed = today.getFullYear() * 10000 + (today.getMonth() + 1) * 100 + today.getDate();
    puzzle = buildPuzzle(theme.words, seed);
    issueNo = dayNumber(today) + 1;
  }

  var found = {};        // word -> cell indices
  var hinted = {};       // word -> true, revealed rather than found
  var startedAt = null;
  var elapsed = 0;
  var ticker = null;
  var complete = false;
  var anchor = null;     // first cell of an in-progress selection
  var current = [];      // cells currently highlighted

  var app = document.getElementById("app");
  var live = document.getElementById("live");
  document.getElementById("issue").textContent = "No. " + issueNo + " · " + today.toDateString();

  function remaining() {
    return theme.words.filter(function (w) { return !found[w]; });
  }
  function fmt(s) {
    var m = Math.floor(s / 60);
    return m + ":" + String(s % 60).padStart(2, "0");
  }
  function say(msg) { live.textContent = msg; }

  /* ---------- selection geometry ---------- */

  function pathBetween(a, b) {
    var x1 = a % SIZE, y1 = Math.floor(a / SIZE);
    var x2 = b % SIZE, y2 = Math.floor(b / SIZE);
    var dx = Math.sign(x2 - x1), dy = Math.sign(y2 - y1);
    var lx = Math.abs(x2 - x1), ly = Math.abs(y2 - y1);
    if (lx !== 0 && ly !== 0 && lx !== ly) return null;   // not a straight line
    var len = Math.max(lx, ly), path = [];
    for (var i = 0; i <= len; i++) path.push((y1 + dy * i) * SIZE + (x1 + dx * i));
    return path;
  }

  function letters(path) {
    return path.map(function (i) { return puzzle.grid[Math.floor(i / SIZE)][i % SIZE]; }).join("");
  }

  var firstWordSent = false, firstAttemptSent = false;

  function commit(path) {
    if (!path || path.length < 2) return false;
    var word = letters(path);
    var reversed = word.split("").reverse().join("");
    var hit = remaining().filter(function (w) { return w === word || w === reversed; })[0];
    if (!hit) return false;
    found[hit] = path.slice();
    if (!firstWordSent) { firstWordSent = true; track("first_word", { issue: issueNo }); }
    say(hit + " found. " + remaining().length + " to go.");
    if (remaining().length === 0) finish();
    return true;
  }

  /* ---------- timing ---------- */

  function beginTimer() {
    if (startedAt !== null) return;
    startedAt = Date.now();
    ticker = setInterval(function () {
      elapsed = Math.floor((Date.now() - startedAt) / 1000);
      var el = document.getElementById("clock");
      if (el) el.textContent = fmt(elapsed);
    }, 1000);
  }

  function finish() {
    complete = true;
    if (ticker) { clearInterval(ticker); ticker = null; }
    if (startedAt !== null) elapsed = Math.floor((Date.now() - startedAt) / 1000);
    if (!DAY) recordStreak();
    track("puzzle_completed", { issue: issueNo, seconds: elapsed, hints: Object.keys(hinted).length });
    renderDone();
  }

  /* ---------- streak (this device only, and labelled as such) ---------- */

  function store(key, value) {
    try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); }
    catch (e) { return null; }
  }

  function recordStreak() {
    var last = store("dc_last_day");
    var streak = parseInt(store("dc_streak") || "0", 10);
    var n = dayNumber(today);
    if (last === String(n)) return;
    streak = (last !== null && parseInt(last, 10) === n - 1) ? streak + 1 : 1;
    store("dc_streak", String(streak));
    store("dc_last_day", String(n));
  }

  function currentStreak() {
    var last = store("dc_last_day");
    var streak = parseInt(store("dc_streak") || "0", 10);
    if (last === null) return 0;
    var n = dayNumber(today), l = parseInt(last, 10);
    return (l === n || l === n - 1) ? streak : 0;
  }

  /* ---------- analytics ---------- */
  /* Anonymous counts only: an event name goes to our own Netlify function, which
     keeps a per-day tally. No cookie, no identifier, no IP is stored. Plausible
     is still called if it is ever configured. */

  // A past day's page counts only these, under names of their own, so the
  // home page's numbers stay about today's puzzle.
  var PAST_EVENTS = { visit: "past_visit", visit_from_pin: "past_from_pin", puzzle_completed: "past_solved" };

  function track(name, props) {
    if (DAY) { name = PAST_EVENTS[name]; if (!name) return; }
    if (typeof window.plausible === "function") window.plausible(name, { props: props || {} });
    try {
      var payload = JSON.stringify({ name: name });
      var url = "/.netlify/functions/event";
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([payload], { type: "application/json" }));
      } else if (window.fetch) {
        fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload,
          keepalive: true
        }).catch(function () {});
      }
    } catch (e) {}
  }

  /* ---------- rendering ---------- */

  function cellClass(i) {
    var cls = "cell";
    if (current.indexOf(i) !== -1) cls += " sel";
    for (var w in found) if (found[w].indexOf(i) !== -1) return cls + (hinted[w] ? " hint" : " found");
    return cls;
  }

  function renderPlay() {
    var cells = "";
    for (var y = 0; y < SIZE; y++) for (var x = 0; x < SIZE; x++) {
      var i = y * SIZE + x;
      cells += '<button class="' + cellClass(i) + '" data-i="' + i + '" type="button" ' +
               'aria-label="Row ' + (y + 1) + ', column ' + (x + 1) + ', letter ' + puzzle.grid[y][x] + '">' +
               puzzle.grid[y][x] + '</button>';
    }
    var words = theme.words.map(function (w) {
      return '<div class="word' + (found[w] ? " done" : "") + '">' + w + "</div>";
    }).join("");

    app.innerHTML =
      '<section class="card"><h2>' + esc(theme.title) + "</h2><p>" + esc(theme.note) + "</p></section>" +
      '<div class="status"><span>Time <span id="clock">' + fmt(elapsed) + "</span></span>" +
      "<span>Found " + Object.keys(found).length + " of " + theme.words.length + "</span></div>" +
      '<div class="board" id="board"><div class="grid" id="grid">' + cells + "</div></div>" +
      '<div class="words">' + words + "</div>" +
      '<div class="controls">' +
      '<button class="btn btn-ghost" id="restart" type="button">Start over</button>' +
      '<button class="btn btn-primary" id="reveal" type="button">Reveal a word</button>' +
      "</div>";

    wireGrid();
    document.getElementById("restart").onclick = restart;
    document.getElementById("reveal").onclick = revealOne;
    var rb = document.getElementById("restart");
    rb.disabled = Object.keys(found).length === 0 && startedAt === null;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function paint() {
    var nodes = document.querySelectorAll(".cell");
    for (var k = 0; k < nodes.length; k++) nodes[k].className = cellClass(Number(nodes[k].dataset.i));
    var st = document.querySelector(".status");
    if (st) st.children[1].textContent = "Found " + Object.keys(found).length + " of " + theme.words.length;
    var ws = document.querySelectorAll(".word");
    for (var j = 0; j < ws.length; j++) {
      ws[j].className = "word" + (found[ws[j].textContent] ? " done" : "");
    }
    var rb = document.getElementById("restart");
    if (rb) rb.disabled = Object.keys(found).length === 0 && startedAt === null;
  }

  function indexFromPoint(clientX, clientY) {
    var el = document.elementFromPoint(clientX, clientY);
    if (el && el.classList && el.classList.contains("cell")) return Number(el.dataset.i);
    return null;
  }

  function wireGrid() {
    var grid = document.getElementById("grid");
    var dragging = false;

    function start(i) {
      beginTimer();
      dragging = true; anchor = i; current = [i]; paint();
    }
    function move(i) {
      if (!dragging || anchor === null || i === null) return;
      var p = pathBetween(anchor, i);
      if (p) { current = p; paint(); }
    }
    function end() {
      if (!dragging) return;
      dragging = false;
      if (!firstAttemptSent) { firstAttemptSent = true; track("first_attempt", { issue: issueNo }); }
      var matched = commit(current);
      current = []; anchor = null;
      if (!complete) paint();
    }

    grid.addEventListener("pointerdown", function (e) {
      var i = indexFromPoint(e.clientX, e.clientY);
      if (i === null) return;
      e.preventDefault();
      grid.setPointerCapture(e.pointerId);
      start(i);
    });
    grid.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      e.preventDefault();
      move(indexFromPoint(e.clientX, e.clientY));
    });
    grid.addEventListener("pointerup", end);
    grid.addEventListener("pointercancel", function () { dragging = false; current = []; anchor = null; paint(); });

    // Keyboard and assistive route: focus a cell, press Enter to set the start, Enter again to set the end.
    grid.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        if (cancelSelection()) say("Selection cancelled.");
        return;
      }
      if (e.key !== "Enter" && e.key !== " ") return;
      var el = document.activeElement;
      if (!el || !el.classList.contains("cell")) return;
      e.preventDefault();
      var i = Number(el.dataset.i);
      beginTimer();
      if (anchor === null) { anchor = i; current = [i]; say("Start of word set. Move to the last letter and press Enter."); }
      else {
        var p = pathBetween(anchor, i);
        if (!p) { say("Words run in a straight line. Try again."); }
        else { current = p; if (!firstAttemptSent) { firstAttemptSent = true; track("first_attempt", { issue: issueNo }); } if (!commit(p)) say("That is not one of today's words."); }
        anchor = null; current = [];
      }
      if (!complete) paint();
    });
  }

  function cancelSelection() {
    if (anchor === null && current.length === 0) return false;
    anchor = null; current = [];
    paint();
    return true;
  }

  // Same puzzle, fresh attempt: today's grid never changes, so only progress resets.
  function restart() {
    found = {}; hinted = {};
    anchor = null; current = [];
    complete = false;
    if (ticker) { clearInterval(ticker); ticker = null; }
    startedAt = null; elapsed = 0;
    say("Cleared. The puzzle is the same; your progress has been reset.");
    track("restarted", { issue: issueNo });
    renderPlay();
  }

  function revealOne() {
    var left = remaining();
    if (!left.length) return;
    var word = left[0];
    found[word] = puzzle.spots[word].slice();
    hinted[word] = true;
    beginTimer();
    say(word + " revealed.");
    track("hint_used", { issue: issueNo });
    if (remaining().length === 0) finish(); else paint();
  }

  function emojiRow() {
    return theme.words.map(function (w) { return hinted[w] ? "🟨" : "🟩"; }).join("");
  }

  function shareText() {
    return "The Daily Clue No. " + issueNo + " — " + theme.title + "\n" +
           emojiRow() + "\n" + fmt(elapsed) + "\nhearthandclue.com" + (DAY ? "/daily/" + issueNo + "/" : "");
  }

  function renderDone() {
    var solvedUnaided = theme.words.length - Object.keys(hinted).length;
    var streak = DAY ? 0 : currentStreak();
    var shop = theme.url
      ? '<div class="shop-note">Liked this one? ' +
        esc(theme.cta || ("There is a full " + theme.subject + " book — 55 puzzles, print at home.")) +
        ' <a href="' + esc(theme.url) +
        '" target="_blank" rel="noopener">See the book</a></div>'
      : "";

    app.innerHTML =
      '<div class="done-panel">' +
      "<h2>Solved</h2>" +
      '<p class="done-sub">' + esc(theme.title) + "</p>" +
      '<div class="figures">' +
      '<div><div class="figure-label">Time</div><div class="figure-value">' + fmt(elapsed) + "</div></div>" +
      '<div><div class="figure-label">Unaided</div><div class="figure-value">' + solvedUnaided + "/" + theme.words.length + "</div></div>" +
      (streak > 1 ? '<div><div class="figure-label">Day streak</div><div class="figure-value">' + streak + "</div></div>" : "") +
      "</div>" +
      '<div class="emoji-grid">' + emojiRow() + "</div>" +
      '<div class="controls">' +
      '<button class="btn btn-primary" id="share" type="button">Share result</button>' +
      '<button class="btn btn-ghost" id="review" type="button">See the grid</button>' +
      "</div>" +
      shop +
      nextLine() +
      "</div>";

    document.getElementById("share").onclick = doShare;
    document.getElementById("review").onclick = function () { complete = false; renderPlay(); paint(); };
  }

  function nextLine() {
    if (DAY) {
      return '<p class="tomorrow"><a href="/">Play today\'s puzzle</a> &middot; <a href="/daily/">All past puzzles</a></p>';
    }
    var y = issueNo - 1;
    return '<p class="tomorrow">A new puzzle at midnight, wherever you are.' +
      (y >= ARCHIVE_FROM ? ' Missed one? <a href="/daily/' + y + '/">Play yesterday\'s</a>.' : "") + "</p>";
  }

  function toast(msg) {
    var t = document.createElement("div");
    t.className = "toast"; t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 1800);
  }

  function doShare() {
    var text = shareText();
    if (navigator.share) {
      navigator.share({ text: text }).then(function () { track("result_shared", { how: "sheet" }); }).catch(function () {});
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        toast("Result copied");
        track("result_shared", { how: "clipboard" });
      }).catch(function () { toast("Could not copy"); });
      return;
    }
    toast("Copying is not available here");
  }

  /* ---------- go ---------- */

  if (!puzzle) {
    app.innerHTML = '<section class="card"><h2>Today\'s puzzle did not build</h2>' +
      "<p>Try again in a moment, or come back tomorrow for a fresh one.</p></section>";
  } else {
    renderPlay();
    track("visit");
    if (/[?&]src=pin(&|$)/.test(location.search)) track("visit_from_pin");
  }
})();
