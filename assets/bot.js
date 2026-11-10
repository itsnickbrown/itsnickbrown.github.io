// "Ask about my work" bot. Runs fully in the browser: no API key, no server.
// It scores each answer by word overlap with the question (plus synonyms) and
// returns the best match. Answers are written from the case studies on this site.
(function () {
  const BASE = document.currentScript.dataset.base || '';
  const L = (path, text) => `<a href="${BASE}${path}">${text}</a>`;

  const KB = [
    {k: 'who nick about background summary yourself intro introduce experience career', a: () =>
      `Nick Brown is a channel manager whose career runs through IT, compliance, contracts, distribution and channel sales. He most recently managed about 1,600 smaller reseller partners for a network test and security tools vendor that sells only through distribution. Before that he was a vendor manager and strategic planner at a distributor, so he has worked both sides of the vendor and distributor relationship. This site shows the AI and data work he built in that role.`},
    {k: 'ai claude how use llm tools approach workflow pair program prompt', a: () =>
      `Nick uses Claude as a working partner. He writes the rules and definitions, Claude helps write the code, and he checks every number against the source. He also built 11+ reusable Claude skills for recurring work (POS analysis, partner vetting, account plans, weekly reports) and a context file so every session starts with his accounts, channel model and writing rules. See ${L('projects/claude-skills.html', 'Claude skills and AI workflow')}.`},
    {k: 'python code scripts programming language stack tech built', a: () =>
      `Most of the work is Python (csv, openpyxl, json) feeding self-contained HTML pages with Chart.js. A one-click batch file runs the whole chain each morning: scrub new distributor files, append to the POS ledger, rebuild the Excel dashboard, the tracker and the insights page. The code for each piece is on its project page and in the ${L('code/', 'code folder')}.`},
    {k: 'dashboard insights partner page month picker repeat returning new gone quiet', a: () =>
      `The Partner Insights page answers who is buying, who is new, who came back and who went quiet, for any month. Python embeds the data and the browser does the month math, so the picker re-anchors every card, chart and table without a rebuild. A BDR used its Declining, Stopped and Gone Quiet buckets to work 336 partners in three waves. ${L('projects/partner-insights.html', 'Read it')} or ${L('demos/partner-insights.html', 'open the live demo')}.`},
    {k: 'tracker daily projection forecast month end seasonal pace run rate', a: () =>
      `The daily tracker rebuilt itself every morning from distributor POS files. Its month-end projection paces month-to-date revenue against how that calendar month normally books, because July back-loads and August front-loads. A flat run rate gets both wrong. Monthly forecasts used bear, base and bull cases. ${L('projects/daily-tracker.html', 'Read it')} or ${L('demos/tracker.html', 'open the demo')}.`},
    {k: 'data quality clean dedupe duplicate double counting messy fix errors ledger merge', a: () =>
      `Nick found that cumulative distributor files were being added twice, because the line ID hashed raw Excel values (line 3 vs 3.0). One month read 93% high. He fixed the ID and wrote a cleanup script that skips rows it cannot safely tell apart. He also merged about 90 name splits, pulled 79 end users out of the reseller list and backfilled a missing month. ${L('projects/ledger-cleanup.html', 'See the cleanup')}.`},
    {k: 'segment segmentation tiers recency active slipping dormant lapsed target list', a: () =>
      `He replaced revenue bands with recency segments: Active (bought in 90 days), Slipping (4 to 12 months quiet), Dormant (13 to 24) and Lapsed (25+). Recency says who to call next, revenue bands do not. Partners were also tiered as Own It, Convert It and Automate It. ${L('projects/segmentation.html', 'Try the segment explorer')}.`},
    {k: 'attribution impact measure causation selection effect touched untouched baseline proof', a: () =>
      `Partners he touched were up 28.5% on trailing 12 while untouched partners were down 11.1%. He did not claim that as impact. Outreach had just started, so the gap was a selection effect: it proved the targeting picked the right partners. He froze a baseline to rerun once the window was fair. ${L('projects/segmentation.html', 'More on this')}.`},
    {k: 'results numbers revenue quota growth performance achievement win', a: () =>
      `Nick finished at 166% of a $450K monthly quota ($5.4M a year). September was up 7.4% year over year across 90 buying partners. He also ran outreach to about 25 overlap partners, a six-issue partner newsletter, and vetted about a dozen partner applications. Exact revenue figures are left off this site on purpose.`},
    {k: 'skills claude custom list pos analysis vetting escalation email account planning weekly report', a: () =>
      `Custom skills include pos-analysis, partner-vetting, account-planning, weekly-activity-report, escalation-email, contact-finder, cold-email, copy-editing and sales-enablement, plus a branded slide skill for QBR decks. Each one encodes how he actually does the task, so the output starts close to done. ${L('projects/claude-skills.html', 'See the skills')}.`},
    {k: 'vetting partner application approve decline hold inbound reseller qualify', a: () =>
      `His partner vetting rule: never approve on self-reported answers. Verify distributor activity first, ask open questions, flag competing lines and coverage gaps, then recommend approve, hold or decline in one line. ${L('projects/claude-skills.html#vetting', 'Try the vetting demo')}.`},
    {k: 'offer builder salon color sales tool configurator order erp sap side project consulting consult freelance', a: () =>
      `The Offer Builder is consulting work for a salon color sales rep. The rep walks a new salon through each product line, and the tool maps their picks to promo order codes, sizes one shared starter kit by total units, and produces copy-paste lines for ERP entry. ${L('projects/offer-builder.html', 'Read it')} or ${L('demos/offer-builder.html', 'try it')}.`},
    {k: 'real data confidential fake synthetic masked privacy names numbers', a: () =>
      `Everything in the demos is synthetic. Partner names, end users, invoices and dollars were generated to match the shape of the real ledger, then run through the same code. The ${L('code/make_synthetic_ledger.py', 'generator script')} is public.`},
    {k: 'this site bot chatbot how built work you are', a: () =>
      `This site is static HTML on GitHub Pages. I am a small search bot that runs in your browser. I match your question against answers written from the case studies. There is no AI model behind me and nothing you type leaves the page.`},
    {k: 'contact hire reach email linkedin talk interview resume available', a: () =>
      `Email Nick at <a href="mailto:nicholas.brown.umd@gmail.com">nicholas.brown.umd@gmail.com</a> or find him on <a href="https://www.linkedin.com/in/nick--brown" target="_blank" rel="noopener">LinkedIn</a>. His resume is ${L('resume.html', 'here')}.`},
    {k: 'roles job looking want next position channel enablement operations', a: () =>
      `Nick is looking at channel and partner management, partner enablement, and AI enablement roles, especially ones where AI adoption is part of the job.`},
    {k: 'newsletter campaign marketing email open rate webinar launch', a: () =>
      `He ran a six-issue plain-text partner newsletter (opens 23 to 28%, one short subject hit 67%) and a product launch newsletter that reached about 1,030 people. He also found the old list reached only 30 of 450 buying partners with a 23% hard bounce rate, and rebuilt it from the ledger.`},
    {k: 'excel powerpoint deck qbr report heat map xlsx pptx', a: () =>
      `Alongside the web pages he built Excel deliverables from POS data (YoY reports, monthly heat maps with sparklines, product deep-dives), an Excel dashboard with red/yellow/green partner status, and QBR decks generated from code.`},
  ];
  const SYN = {aio: 'ai', ml: 'ai', gpt: 'ai', chatgpt: 'ai', anthropic: 'claude', py: 'python', viz: 'dashboard',
    chart: 'dashboard', charts: 'dashboard', report: 'dashboard', clean: 'clean', cleanup: 'clean', duplicates: 'duplicate',
    forecasting: 'forecast', predict: 'forecast', projection: 'projection', segments: 'segment', tier: 'tiers',
    hiring: 'hire', job: 'job', jobs: 'job', fake: 'fake', real: 'real', privacy: 'privacy', hello: 'intro', hi: 'intro', hey: 'intro'};
  const STOP = new Set('the a an and or of to in on for is are was were do does did how what why who with my your his he it this that you me can i about tell show any'.split(' '));
  const toks = s => s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(w => w && !STOP.has(w)).map(w => SYN[w] || w.replace(/s$/, ''));
  const IDX = KB.map(e => new Set(toks(e.k)));
  function answer(q) {
    const t = toks(q);
    let best = -1, score = 0;
    IDX.forEach((set, i) => {
      let s = 0;
      t.forEach(w => { if (set.has(w)) s += 2; else for (const k of set) if (k.length > 3 && (k.startsWith(w) || w.startsWith(k))) { s += 1; break; } });
      if (s > score) { score = s; best = i; }
    });
    if (best < 0 || score < 2) return `I don't have a good answer for that one. Try asking about the dashboards, data cleanup, forecasting, Claude skills, results, or whether the data is real.`;
    return KB[best].a();
  }

  const SUG = ['How does Nick use AI?', 'What results did he get?', 'Is this real data?', 'What was wrong with the data?', 'What Claude skills did he build?'];
  const html = `<button id="botBtn" aria-controls="bot" aria-expanded="false">Ask about my work</button>
  <div id="bot" role="dialog" aria-label="Ask about my work">
    <div class="top"><div><b>Ask about Nick's work</b><span>Runs in your browser. Answers come from this site.</span></div><button id="botX" aria-label="Close">&times;</button></div>
    <div id="botLog" aria-live="polite"></div>
    <form id="botForm"><input id="botIn" placeholder="Ask a question" autocomplete="off"><button>Ask</button></form>
  </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  const log = document.getElementById('botLog'), box = document.getElementById('bot'), btn = document.getElementById('botBtn');
  function add(text, who) { const d = document.createElement('div'); d.className = 'msg ' + who; d.innerHTML = text; log.appendChild(d); log.scrollTop = log.scrollHeight; }
  function sugs() { const d = document.createElement('div'); d.className = 'sugs'; d.innerHTML = SUG.map(s => `<button type="button">${s}</button>`).join(''); d.querySelectorAll('button').forEach(b => b.onclick = () => ask(b.textContent)); log.appendChild(d); }
  function ask(q) { if (!q.trim()) return; add(q.replace(/</g, '&lt;'), 'me'); setTimeout(() => add(answer(q), 'bot'), 180); }
  let started = false;
  function toggle(open) { box.classList.toggle('on', open); btn.setAttribute('aria-expanded', open);
    if (open && !started) { started = true; add(`Hi. I can answer questions about Nick's projects, how he uses AI, and what he found in the data. Pick one or type your own.`, 'bot'); sugs(); }
    if (open) document.getElementById('botIn').focus(); }
  btn.onclick = () => toggle(!box.classList.contains('on'));
  document.getElementById('botX').onclick = () => toggle(false);
  document.getElementById('botForm').onsubmit = e => { e.preventDefault(); const i = document.getElementById('botIn'); ask(i.value); i.value = ''; };
  document.querySelectorAll('[data-ask]').forEach(el => el.onclick = e => { e.preventDefault(); toggle(true); ask(el.dataset.ask); });
  window.__botAnswer = answer;
})();
