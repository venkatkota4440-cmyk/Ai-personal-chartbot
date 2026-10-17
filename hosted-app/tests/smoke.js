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
  var store = {};
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
