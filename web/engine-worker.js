/* OpenPPC's engine worker: Pyodide and the openppc package run here, off the page's thread, so a large
   export never freezes the tab. app.js talks to it with messages:

     page -> worker  {id, op: 'write', path, bytes}   put a file in the in-memory file system
                     {id, op: 'call', fn, args}       call openppc.webapi.fn(*args)
     worker -> page  {type: 'status', text}           while starting
                     {type: 'ready', meta}            started; meta is webapi.meta()
                     {type: 'failed', error}          could not start
                     {id, ok: true, result}           a call's answer
                     {id, ok: false, error}           a call that failed

   Python can't be interrupted mid-call, so Stop terminates this worker and the page starts a new one.
   A module worker, because Pyodide's module build will not start in a classic one. */

const PYODIDE_INDEX = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/';
const PYODIDE_SRI = 'sha384-Lp79fMwxa4n2BLtugpUAoQMlbxIdg8iCUiP1r3h7nJLkQjwlXT1JzZTeHVL+f4Dg';  // pyodide.mjs

let py = null;
let api = null;

const reply = (message) => postMessage(message);
const errorText = (e) => (e instanceof Error && e.message ? e.message : String(e));

async function loadRuntime() {
  // import() can't check integrity, so the runtime is fetched with its hash and imported from a blob
  const res = await fetch(PYODIDE_INDEX + 'pyodide.mjs', { integrity: PYODIDE_SRI, credentials: 'omit' });
  if (!res.ok) throw new Error('the Python runtime did not download. Check your connection.');
  const url = URL.createObjectURL(new Blob([await res.text()], { type: 'text/javascript' }));
  try {
    const { loadPyodide } = await import(url);
    return await loadPyodide({ indexURL: PYODIDE_INDEX });
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function start() {
  try {
    const runtime = await loadRuntime();
    reply({ type: 'status', text: 'Loading the OpenPPC engine…' });
    await import('./engine.js');  // the openppc package and the samples, as globalThis.OPENPPC_BUNDLE
    for (const [path, source] of Object.entries(self.OPENPPC_BUNDLE.files)) {
      runtime.FS.mkdirTree('/app/' + path.split('/').slice(0, -1).join('/'));
      runtime.FS.writeFile('/app/' + path, source);
    }
    runtime.FS.mkdirTree('/uploads');
    runtime.runPython("import sys\nsys.path.insert(0, '/app')");
    py = runtime;
    api = runtime.pyimport('openppc.webapi');
    reply({ type: 'ready', meta: JSON.parse(String(api.meta())) });
  } catch (e) {
    reply({ type: 'failed', error: errorText(e) });
  }
}

const started = start();

self.onmessage = async (e) => {
  const m = e.data;
  await started;
  try {
    if (!py || !api) throw new Error('the checker did not start');
    let result = null;
    if (m.op === 'write') {
      py.FS.writeFile(m.path, m.bytes);
    } else if (m.op === 'call') {
      const fn = api[m.fn];
      if (typeof fn !== 'function') throw new Error(`unknown engine function ${m.fn}`);
      result = fn(...m.args);
      if (result && typeof result === 'object' && typeof result.toJs === 'function') result = result.toJs();
    } else {
      throw new Error(`unknown message ${m.op}`);
    }
    reply({ id: m.id, ok: true, result });
  } catch (err) {
    reply({ id: m.id, ok: false, error: errorText(err) });
  }
};
