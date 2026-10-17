// Drives the app in Chromium with stand-in connectors, so every flow is
// exercised without touching a real account.
// Usage: PLAYWRIGHT_CORE=<path to playwright-core> CHROMIUM=<chrome binary> node smoke.js
const { chromium } = require(process.env.PLAYWRIGHT_CORE || "playwright-core");
const fs = require("fs");
const path = require("path");

const APP = fs.readFileSync(path.join(__dirname, "..", "agent-app.html"), "utf8");

const STUB = `
<script>
(function () {
  var calls = [];
  window.__calls = calls;
  var mode0 = window.__mode || {};
  var store = JSON.parse(JSON.stringify(mode0.seed || {}));
  function coll(name) {
    store[name] = store[name] || {};
    var subs = [];
    function emit() {
      var docs = Object.keys(store[name]).map(function (k) { return { id: k, data: function () { return store[name][k]; } }; });
      subs.forEach(function (fn) { fn({ docs: docs }); });
    }
    return {
      doc: function (id) { return {
        set: function (b) { store[name][id] = JSON.parse(JSON.stringify(b)); setTimeout(emit, 0); return Promise.resolve(); },
        delete: function () { delete store[name][id]; setTimeout(emit, 0); return Promise.resolve(); }
      }; },
      onSnapshot: function (fn) { subs.push(fn); setTimeout(emit, 0); return function () {}; }
    };
  }
  window.__store = store;
  var mode = window.__mode || {};
  var mcp = {
    callTool: function (server, tool, input) {
      calls.push({ server: server, tool: tool, input: input });
      var r = function (p) { return Promise.resolve({ content: [], payload: p }); };
      if (tool === "profiles_list") return r({ targets: [
        { id: "IG1", name: "my_insta", platform: "instagram", profile_group_id: "G" },
        { id: "FB1", name: "My Page", platform: "facebook", profile_group_id: "G" },
        { id: "LI1", name: "Me on LinkedIn", platform: "linkedin", profile_group_id: "G" }
      ] });
      if (tool === "get_file_permissions") return r({ permissions: [{ type: "user", role: "owner" }] });
      if (tool === "search_files") return r({ files: [{ id: "F1", title: "sunset.jpg", mimeType: "image/jpeg", createdTime: "2026-10-17T05:00:00Z" }] });
      if (tool === "post_publish") return r({ post_id: "P1", status: "pending" });
      if (tool === "post_status") return r({ post_id: "P1", overall_status: "processing", scheduled_at: input && "2099-01-01T00:00:00Z",
        platforms: [{ platform: "instagram", status: "pending" }, { platform: "facebook", status: "pending" }] });
      if (tool === "post_delete") return r({ deleted: true });
      if (tool === "dm_chats_list") {
        if (mode.dmOff) return Promise.reject({ code: "tool_error", message: "Direct messages are opt-in. Please enable them on https://app.postproxy.dev/chats." });
        return r({ chats: [
          { id: "C1", participant_name: "Ravi", last_message_at: "2026-10-17T07:00:00Z", within_messaging_window: true },
          { id: "C2", participant_name: "Old friend", last_message_at: "2026-09-01T07:00:00Z", within_messaging_window: false }
        ] });
      }
      if (tool === "dm_message_send") return r({ id: "M1", status: "pending" });
      return Promise.reject({ code: "bad_request", message: "unexpected tool " + tool });
    }
  };
  window.claude = { use: function (n) {
    if (n === "db") return Promise.resolve({ collection: coll });
    if (n === "mcp") return Promise.resolve(mcp);
    return Promise.resolve(null);
  } };
})();
</script>`;

function page(mode) {
  return "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=390'></head><body>" +
    "<script>window.__mode=" + JSON.stringify(mode || {}) + "</script>" + STUB + APP + "</body></html>";
}

let failures = 0;
function check(cond, label) {
  console.log((cond ? "  PASS " : "  FAIL ") + label);
  if (!cond) failures++;
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));

  await p.setContent(page({}));
  await p.waitForTimeout(800);

  console.log("Today");
  const today = await p.textContent("main");
  check(/Finish setting up/.test(today), "setup card shows");
  check(/Share your photo folder/.test(today), "private Drive folder is flagged");
  check(/3 accounts to confirm/.test(today), "unconfirmed accounts are counted");

  console.log("Posts: accounts");
  await p.click("nav >> text=Posts");
  await p.waitForTimeout(200);
  let posts = await p.textContent("main");
  check(/my_insta/.test(posts) && /My Page/.test(posts) && /Me on LinkedIn/.test(posts), "all three platforms listed");
  const confirms = await p.$$("main button:has-text('Confirm')");
  check(confirms.length === 3, "each account has Confirm");
  for (let i = 0; i < 3; i++) { await p.click("main button:has-text('Confirm') >> nth=0"); await p.waitForTimeout(150); }
  posts = await p.textContent("main");
  check((posts.match(/Confirmed/g) || []).length >= 3, "all three now confirmed");

  console.log("Posts: compose rules");
  // Story: LinkedIn must be disabled.
  await p.click("main .seg >> text=Story");
  await p.waitForTimeout(150);
  const liBox = await p.$("main [role=checkbox][aria-label*='LinkedIn']");
  check(liBox && (await liBox.isDisabled()), "LinkedIn cannot take a story");
  await p.click("main .seg >> text=Post");
  await p.waitForTimeout(150);
  // Pick IG + FB, no media -> must refuse.
  await p.click("main [role=checkbox][aria-label*='Instagram']");
  await p.click("main [role=checkbox][aria-label*='Facebook']");
  await p.fill("#compose-caption", "Evening walk");
  await p.click("main button:has-text('Review and approve')");
  await p.waitForTimeout(200);
  check(/Instagram cannot post without a photo/.test(await p.textContent("main")), "Instagram without media is refused before scheduling");

  // Choose media from Drive.
  await p.click("main button:has-text('Choose from Drive')");
  await p.waitForTimeout(250);
  await p.click("main button:has-text('Use')");
  await p.waitForTimeout(200);
  check(/sunset\.jpg/.test(await p.textContent("main")), "Drive photo picked");

  // Schedule for tomorrow 21:00.
  const tmr = await p.evaluate(() => { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10); });
  await p.fill("main input[type=date]", tmr);
  await p.fill("main input[type=time]", "21:00");
  await p.click("main button:has-text('Review and approve')");
  await p.waitForTimeout(400);
  const sheet = await p.textContent("dialog");
  check(/my_insta/.test(sheet) && /My Page/.test(sheet), "sheet names both accounts");
  check(/Postproxy publishes it then/.test(sheet), "sheet says Postproxy publishes at the time");
  check(/"schedule":/.test(sheet), "arguments include schedule");
  check(/drive\.usercontent\.google\.com\/download/.test(sheet), "media uses the download endpoint");
  await p.click("dialog button:has-text('Approve and schedule')");
  await p.waitForTimeout(400);
  const pub = await p.evaluate(() => window.__calls.filter((c) => c.tool === "post_publish"));
  check(pub.length === 1, "post_publish called exactly once");
  const inp = pub[0] && pub[0].input;
  check(inp && inp.profiles.length === 2 && inp.profiles.includes("IG1") && inp.profiles.includes("FB1"), "both profiles sent");
  check(inp && inp.platforms && inp.platforms.instagram.format === "post" && inp.platforms.facebook.format === "post", "per-platform formats sent");
  check(inp && typeof inp.schedule === "string" && Date.parse(inp.schedule) > Date.now(), "future schedule sent to Postproxy");
  check(inp && inp.content === "Evening walk", "caption sent");
  check(inp && /^[0-9a-f]{64}$/.test(inp.idempotency_key), "idempotency key is the fingerprint");
  posts = await p.textContent("main");
  check(/Scheduled/.test(posts) && /Cancel/.test(posts), "scheduled post listed with Cancel");

  console.log("Posts: cancel");
  await p.click("main button:has-text('Cancel')");
  await p.waitForTimeout(300);
  const del = await p.evaluate(() => window.__calls.filter((c) => c.tool === "post_delete"));
  check(del.length === 1 && del[0].input.post_id === "P1", "post_delete called for that job");
  check(/Cancelled/.test(await p.textContent("main")), "shows Cancelled");

  console.log("Story rules");
  await p.click("main .seg >> text=Story");
  await p.waitForTimeout(150);
  check(!(await p.$("#compose-caption")), "story hides caption");

  console.log("Messages");
  await p.click("nav >> text=Messages");
  await p.waitForTimeout(500);
  let msgs = await p.textContent("main");
  check(/Ravi/.test(msgs) && /Old friend/.test(msgs), "conversations listed");
  check(/window closed/.test(msgs), "closed 24h window is shown");
  const replies = await p.$$("main button:has-text('Reply')");
  const disabled = [];
  for (const r of replies) disabled.push(await r.isDisabled());
  check(disabled.includes(true) && disabled.includes(false), "Reply disabled only where the window is closed");
  await p.click("main button:has-text('Reply'):not([disabled]) >> nth=0");
  await p.waitForTimeout(150);
  await p.fill("dialog textarea", "See you at 7!");
  await p.click("dialog button:has-text('Review')");
  await p.waitForTimeout(300);
  check(/This sends a real message/.test(await p.textContent("dialog")), "message approval warns it is real");
  await p.click("dialog button:has-text('Send now')");
  await p.waitForTimeout(300);
  const sends = await p.evaluate(() => window.__calls.filter((c) => c.tool === "dm_message_send"));
  check(sends.length >= 1 && sends[0].input.body === "See you at 7!", "dm_message_send called with the text");
  check(sends.every((s) => !s.input.tag), "never uses the HUMAN_AGENT tag");

  console.log("Messages switched off");
  const p2 = await ctx.newPage();
  p2.on("pageerror", (e) => errors.push(String(e)));
  await p2.setContent(page({ dmOff: true }));
  await p2.waitForTimeout(600);
  await p2.evaluate(() => { window.__store.settings = window.__store.settings || {}; });
  await p2.click("nav >> text=Posts");
  await p2.waitForTimeout(200);
  for (let i = 0; i < 3; i++) { await p2.click("main button:has-text('Confirm') >> nth=0"); await p2.waitForTimeout(120); }
  await p2.click("nav >> text=Messages");
  await p2.waitForTimeout(500);
  check(/Messages are switched off/.test(await p2.textContent("main")), "opt-in error gets its own fix");


  console.log("Wrong account");
  const yday = new Date(Date.now() - 26 * 3600 * 1000).toISOString();
  const p3 = await ctx.newPage();
  p3.on("pageerror", (e) => errors.push(String(e)));
  await p3.setContent(page({ seed: {
    settings: { accounts: { confirmed: { FB1: { name: "My Page", platform: "facebook" } },
      wrong: { IG1: { name: "my_insta", platform: "instagram" } }, expected: { instagram: "real_insta" } } },
    tasks: { T1: { title: "Gym", done: true, doneAt: yday, repeat: "daily", createdAt: yday },
             T2: { title: "One-off", done: true, doneAt: yday, repeat: "", createdAt: yday } }
  } }));
  await p3.waitForTimeout(2200);
  let t3 = await p3.textContent("main");
  check(/Connect @real_insta/.test(t3), "missing real account is asked for");
  check(/Disconnect my_insta/.test(t3), "wrong account flagged for removal");
  check(/1 account to confirm/.test(t3), "only the genuinely unconfirmed account is counted, not the wrong one");
  const tasks = await p3.evaluate(() => window.__store.tasks);
  check(tasks.T1.done === false, "daily task ticked yesterday is unticked today");
  check(tasks.T2.done === true, "one-off task stays done");
  await p3.click("nav >> text=Posts");
  await p3.waitForTimeout(300);
  t3 = await p3.textContent("main");
  check(/Not mine/.test(t3) && /never posts here/.test(t3), "wrong account labelled in Accounts");
  const igBox = await p3.$("main [role=checkbox][aria-label*='Instagram']");
  check(!igBox, "wrong account cannot be picked for a post");

  console.log("Daily routine");
  await p3.click("nav >> text=Today");
  await p3.waitForTimeout(200);
  await p3.fill("main input[aria-label='Daily post time']", "21:00");
  await p3.click("main button:has-text('Add post time')");
  await p3.waitForTimeout(250);
  await p3.fill("main input[aria-label='Daily post time']", "09:00");
  await p3.click("main button:has-text('Add post time')");
  await p3.waitForTimeout(250);
  let daily = await p3.evaluate(() => window.__store.settings.daily);
  check(daily && daily.postTimes.join(",") === "09:00,21:00", "two daily post times saved, sorted");
  await p3.click("main button:has-text('Turn on')");
  await p3.waitForTimeout(400);
  const brief = await p3.evaluate(() => Object.values(window.__store.actions || {}).filter((a) => a.type === "daily_briefing"));
  check(brief.length === 1 && brief[0].repeat === "daily" && Date.parse(brief[0].dueAt) > Date.now(), "briefing scheduled once, in the future");
  await p3.click("main button:has-text('Turn on'), main button:has-text('Turn off')");
  await p3.waitForTimeout(300);
  const brief2 = await p3.evaluate(() => Object.values(window.__store.actions || {}).filter((a) => a.type === "daily_briefing"));
  check(brief2.length === 0, "turning the briefing off removes it");

  // Two posts into daily slots: each takes a different, later slot.
  await p3.click("nav >> text=Posts");
  await p3.waitForTimeout(250);
  async function slotPost(caption) {
    const fb = await p3.$("main [role=checkbox][aria-label*='Facebook']");
    if ((await fb.getAttribute("aria-checked")) !== "true") await fb.click();
    await p3.fill("#compose-caption", caption);
    await p3.click("main .seg >> text=Next daily slot");
    await p3.waitForTimeout(150);
    await p3.click("main button:has-text('Review and approve')");
    await p3.waitForTimeout(350);
    const errText = await p3.evaluate(() => { const e = document.querySelector("main .err"); return e && !e.hidden ? e.textContent : ""; });
    const dlgOpen = await p3.evaluate(() => document.getElementById("sheet").open);
    if (!dlgOpen) { console.log("    debug: dialog not open; form error =", JSON.stringify(errText)); throw new Error("no dialog"); }
    await p3.click("dialog button:has-text('Approve and schedule')");
    await p3.waitForTimeout(400);
  }
  await slotPost("first");
  await slotPost("second");
  const sched = await p3.evaluate(() => window.__calls.filter((c) => c.tool === "post_publish").map((c) => c.input.schedule));
  check(sched.length === 2 && sched[0] && sched[1] && sched[0] !== sched[1], "two posts got two different slots");
  const hours = sched.map((x) => new Date(x).getHours() + ":" + String(new Date(x).getMinutes()).padStart(2, "0"));
  check(hours.every((h) => h === "9:00" || h === "21:00"), "slots are the daily post times (" + hours.join(", ") + ")");
  check(Date.parse(sched[1]) > Date.parse(sched[0]), "second post is after the first");

  console.log("Tabs render without errors");
  for (const t of ["Today", "Chat", "Posts", "Messages", "Approvals"]) {
    await p.click("nav >> text=" + t);
    await p.waitForTimeout(150);
  }
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check(!overflow, "no horizontal overflow at 390px");
  check(errors.length === 0, "no page errors" + (errors.length ? ": " + errors.join(" | ") : ""));

  await p.screenshot({ path: path.join(__dirname, "posts.png"), fullPage: true });
  await browser.close();
  console.log(failures ? "\n" + failures + " FAILED" : "\nALL PASSED");
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
