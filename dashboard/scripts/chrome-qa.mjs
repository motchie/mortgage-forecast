import { writeFile } from "node:fs/promises";

const endpoint = process.env.CHROME_DEBUG_URL ?? "http://127.0.0.1:9222";
const baseUrl = process.env.DASHBOARD_URL ?? "http://127.0.0.1:5173";
const screenshotDir = process.env.SCREENSHOT_DIR;

const target = await fetch(`${endpoint}/json/new?${encodeURIComponent(baseUrl)}`, { method: "PUT" }).then((response) => response.json());
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let nextId = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(`${message.error.message}: ${message.error.data ?? ""}`));
  else resolve(message.result);
});

function cdp(method, params = {}) {
  const id = ++nextId;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const evaluate = async (expression) => (await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result.value;

await cdp("Page.enable");
await cdp("Runtime.enable");
await cdp("Accessibility.enable");
await cdp("Page.navigate", { url: baseUrl });
for (let attempt = 0; attempt < 50; attempt += 1) {
  if (await evaluate("document.readyState === 'complete' && Boolean(document.querySelector('h1'))")) break;
  await sleep(100);
}

const viewportResults = [];
for (const width of [320, 375, 390, 430, 768, 1440]) {
  await cdp("Emulation.setDeviceMetricsOverride", { width, height: width < 768 ? 900 : 1000, deviceScaleFactor: 1, mobile: width < 768 });
  await sleep(250);
  const metrics = await evaluate(`(() => {
    const root = document.documentElement;
    const tables = [...document.querySelectorAll('.table-scroll')].map((element) => ({
      label: element.getAttribute('aria-label'),
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      tabIndex: element.tabIndex,
    }));
    const offenders = [...document.querySelectorAll('body *')]
      .filter((element) => !element.closest('.table-scroll'))
      .map((element) => ({ element, rect: element.getBoundingClientRect() }))
      .filter(({ rect }) => rect.right > innerWidth + 1 || rect.left < -1)
      .slice(0, 8)
      .map(({ element, rect }) => ({ tag: element.tagName, className: element.className, left: rect.left, right: rect.right }));
    return {
      innerWidth,
      documentWidth: root.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      pageOverflow: root.scrollWidth > innerWidth + 1,
      offenders,
      scrollableTables: tables.filter((table) => table.scrollWidth > table.clientWidth + 1),
      tableFocusMismatch: tables.filter((table) => (table.scrollWidth > table.clientWidth + 1) !== (table.tabIndex === 0)),
    };
  })()`);
  viewportResults.push({ width, ...metrics });

  if (screenshotDir && (width === 390 || width === 1440)) {
    const screenshot = await cdp("Page.captureScreenshot", { format: "png", fromSurface: true, captureBeyondViewport: false });
    await writeFile(`${screenshotDir}/dashboard-${width}.png`, Buffer.from(screenshot.data, "base64"));
  }
}

await cdp("Emulation.setDeviceMetricsOverride", { width: 640, height: 900, deviceScaleFactor: 1, mobile: false });
await sleep(250);
const zoom200Equivalent = await evaluate(`({
  cssViewportWidth: innerWidth,
  documentWidth: document.documentElement.scrollWidth,
  pageOverflow: document.documentElement.scrollWidth > innerWidth + 1,
  overlappingCards: [...document.querySelectorAll('.metric, .loan-card, .scenario-card')].some((element, index, elements) => elements.slice(index + 1).some((other) => {
    const a = element.getBoundingClientRect(); const b = other.getBoundingClientRect();
    return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  })),
})`);

await cdp("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
await sleep(150);
await evaluate("document.querySelector('.scope-picker select').focus()");
await cdp("Input.dispatchKeyEvent", { type: "keyDown", key: "ArrowDown", code: "ArrowDown", windowsVirtualKeyCode: 40 });
await cdp("Input.dispatchKeyEvent", { type: "keyUp", key: "ArrowDown", code: "ArrowDown", windowsVirtualKeyCode: 40 });
const scopeAfterKeyboard = await evaluate("document.querySelector('.scope-picker select').value");

await evaluate("document.querySelector('.text-button').focus()");
await cdp("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
await cdp("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
await sleep(100);
const tableExpandedByKeyboard = await evaluate("document.querySelector('.text-button').getAttribute('aria-expanded') === 'true'");

await evaluate("document.querySelector('.card-warnings summary').focus()");
await cdp("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
await cdp("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
const warningOpenedByKeyboard = await evaluate("document.querySelector('.card-warnings').open");
const focusIndicator = await evaluate(`(() => { const style = getComputedStyle(document.activeElement); return { tag: document.activeElement.tagName, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth }; })()`);

await cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
const reducedMotion = await evaluate(`({
  matches: matchMedia('(prefers-reduced-motion: reduce)').matches,
  scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
  animationDuration: getComputedStyle(document.querySelector('.scenario-card')).animationDuration,
  transitionDuration: getComputedStyle(document.querySelector('.scenario-card')).transitionDuration,
})`);

await cdp("Emulation.setEmulatedMedia", { features: [{ name: "forced-colors", value: "active" }] });
const forcedColors = await evaluate(`({
  matches: matchMedia('(forced-colors: active)').matches,
  focusOutline: getComputedStyle(document.activeElement).outlineStyle,
  currentScenarioBorder: getComputedStyle(document.querySelector('.scenario-current')).borderStyle,
  assumedScenarioBorder: getComputedStyle(document.querySelector('.scenario-base')).borderStyle,
})`);

const accessibilityTree = await cdp("Accessibility.getFullAXTree");
const axSummary = {
  pageTitle: accessibilityTree.nodes.find((node) => node.role?.value === "RootWebArea")?.name?.value,
  headingCount: accessibilityTree.nodes.filter((node) => node.role?.value === "heading").length,
  buttonNames: accessibilityTree.nodes.filter((node) => node.role?.value === "button").map((node) => node.name?.value),
};

console.log(JSON.stringify({ viewportResults, zoom200Equivalent, keyboard: { scopeAfterKeyboard, tableExpandedByKeyboard, warningOpenedByKeyboard, focusIndicator }, reducedMotion, forcedColors, axSummary }, null, 2));
socket.close();
