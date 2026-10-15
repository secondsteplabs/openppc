// Bundles trace-engine.mjs into one minified script with its licences on top: `node build.mjs` writes
// build/trace-engine.js, `node build.mjs vendor` the copy openppc-online ships. The same inputs give the same bytes, so
// the calibration workflow rebuilds it and checks it is the vendored file.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { build } from 'esbuild';

const require = createRequire(import.meta.url);
const info = (name) => require(`${name}/package.json`);
const licence = (name) => readFileSync(require.resolve(`${name}/LICENSE`), 'utf8').replace(/\r\n/g, '\n').trim();
const engine = info('@paulirish/trace_engine');
const web = info('third-party-web');
const legacy = info('legacy-javascript');
const banner = `/*! OpenPPC's bundle of ${engine.name} ${engine.version} (${engine.license}), with third-party-web
${web.version} (${web.license}) and legacy-javascript ${legacy.version} (${legacy.license}), built by esbuild from
companion/calibration/trace-engine.mjs. Their licences follow.

${engine.name}:
${licence('@paulirish/trace_engine')}

third-party-web:
${licence('third-party-web')}

legacy-javascript: Copyright Google LLC. Licensed under the Apache License, Version 2.0 (the "License"); you may not
use this file except in compliance with the License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0. Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
either express or implied. See the License for the specific language governing permissions and limitations under the
License.
*/`;

const vendor = process.argv[2] === 'vendor';
await build({
  entryPoints: ['trace-engine.mjs'],
  bundle: true,
  format: 'iife',
  minify: true,
  target: 'chrome120',
  legalComments: 'none',
  banner: { js: banner },
  outfile: vendor ? '../openppc_online/siteaudit/vendor/trace-engine.js' : 'build/trace-engine.js',
  logLevel: 'warning',
});
