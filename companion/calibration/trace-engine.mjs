// The DevTools trace engine Lighthouse 13.5 runs (@paulirish/trace_engine, BSD-3), as one script a blank page can
// run: `npm run vendor` writes openppc_online/siteaudit/vendor/trace-engine.js (`npm run build`, build/ for trying it),
// which sets globalThis.openppcTraceEngine. Its insights(events, lanternSettings, hostDPR) runs the engine as
// Lighthouse's core/computed/trace-engine-result.js does and returns, for the load's navigation, each insight's state,
// savings, English title, the checks it failed and up to ITEMS of what it blames, and each URL's cost, as plain JSON.
import * as TraceEngine from '@paulirish/trace_engine';

const ITEMS = 5;
const url = (request) => request?.args?.data?.url;
// What each insight blames: files, or for third parties the companies
const BLAMES = {
  RenderBlocking: (m) => m.renderBlockingRequests?.map(url),
  ImageDelivery: (m) => m.optimizableImages?.map((i) => url(i.request)),
  LCPDiscovery: (m) => [url(m.lcpRequest)],
  LCPBreakdown: (m) => [url(m.lcpRequest)],
  Cache: (m) => m.requests?.map((r) => url(r.request)),
  ModernHTTP: (m) => m.http1Requests?.map(url),
  FontDisplay: (m) => m.fonts?.map((f) => url(f.request)),
  DuplicatedJavaScript: (m) => m.scriptsWithDuplication?.map((s) => s.url),
  LegacyJavaScript: (m) => [...(m.legacyJavaScriptResults?.keys() ?? [])].map((s) => s.url),
  ThirdParties: (m) => m.entitySummaries?.filter((e) => e.entity !== m.firstPartyEntity).map((e) => e.entity?.name),
};
const english = (s) => (typeof s === 'string' ? s : s?.formattedDefault ?? '');

// A failing insight's model, cut to `depth` levels, without trace events' own fields, for reading why it failed
function trimmed(value, depth = 4, seen = new Set()) {
  if (value === null || typeof value !== 'object') return typeof value === 'bigint' ? Number(value) : value;
  if (seen.has(value) || depth === 0) return '…';
  seen.add(value);
  if (value instanceof Map) value = Object.fromEntries(value);
  if (value instanceof Set) value = [...value];
  if (Array.isArray(value)) return value.slice(0, 10).map((v) => trimmed(v, depth - 1, seen));
  if ('ph' in value && 'ts' in value) return { name: value.name, ts: value.ts, dur: value.dur, url: value.args?.data?.url };
  const out = {};
  for (const [k, v] of Object.entries(value)) {
    if (typeof v !== 'function' && k !== 'navigation' && k !== 'createOverlays') out[k] = trimmed(v, depth - 1, seen);
  }
  return out;
}

async function insights(events, lanternSettings, hostDPR, debug = false) {
  const processor = new TraceEngine.Processor.TraceProcessor(TraceEngine.Handlers.ModelHandlers);
  TraceEngine.Helpers.SyntheticEvents.SyntheticEventsManager.createAndActivate(events);
  await processor.parse(events, { lanternSettings, metadata: { hostDPR } });
  const sets = [...(processor.insights ?? new Map()).values()];
  const set = sets.find((s) => s.navigation?.args.data?.navigationId);
  if (!set) return { error: 'no navigation in the trace' };
  const out = {};
  for (const [name, model] of Object.entries(set.model)) {
    const savings = {};
    for (const [metric, value] of Object.entries(model.metricSavings ?? {})) {
      if (Number.isFinite(value)) savings[metric] = value;
    }
    const checks = model.checklist ?? model.data?.checklist ?? {};
    out[name] = {
      state: model.state, title: english(model.title), metricSavings: savings, wastedBytes: model.wastedBytes ?? null,
      failed: Object.values(checks).filter((c) => c && c.value === false).map((c) => english(c.label)),
      items: [...new Set((BLAMES[name]?.(model) ?? []).filter(Boolean))].slice(0, ITEMS),
    };
    if (debug && model.state === 'fail') out[name].model = trimmed(model);
  }
  for (const [name, error] of Object.entries(set.modelErrors)) out[name] = { error: String(error) };
  // Each URL's bytes and main-thread time, as Lighthouse's third-parties insight counts them
  const costs = TraceEngine.Extras.ThirdParties.summarizeByURL(processor.data, set.bounds)
    .filter((s) => s.url && (s.transferSize > 0 || s.mainThreadTime > 0))
    .map((s) => ({ url: s.url, bytes: s.transferSize, ms: s.mainThreadTime }));
  return { url: String(set.url), insights: out, costs };
}

globalThis.openppcTraceEngine = { insights };
