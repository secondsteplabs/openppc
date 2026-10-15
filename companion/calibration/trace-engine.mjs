// The DevTools trace engine Lighthouse 13.5 runs (@paulirish/trace_engine, BSD-3), as one script a blank page can
// run: `npm run build` writes build/trace-engine.js, which sets globalThis.openppcTraceEngine. Its insights(events,
// lanternSettings, hostDPR) runs the engine as Lighthouse's core/computed/trace-engine-result.js does and returns,
// for the load's navigation, each insight's state, metric savings and byte savings, as plain JSON.
import * as TraceEngine from '@paulirish/trace_engine';

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
    out[name] = { state: model.state, metricSavings: savings, wastedBytes: model.wastedBytes ?? null };
    if (debug && model.state === 'fail') out[name].model = trimmed(model);
  }
  for (const [name, error] of Object.entries(set.modelErrors)) out[name] = { error: String(error) };
  return { url: String(set.url), insights: out };
}

globalThis.openppcTraceEngine = { insights };
