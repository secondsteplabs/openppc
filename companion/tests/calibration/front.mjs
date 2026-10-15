// TLS in front of the calibration's fixture server (fixtures.py), so its pages load as most sites do: HTTP/2 on one
// port, and HTTP/1.1 only on another (the HTTP/1.1-only host). Arguments: the key, the certificate, and the fixture
// server's port on 127.0.0.1. Prints the two ports, HTTP/2 first, once both listen.
import http from 'node:http';
import http2 from 'node:http2';
import https from 'node:https';
import { readFileSync } from 'node:fs';

const [keyFile, certFile, upstream] = process.argv.slice(2);
const tls = { key: readFileSync(keyFile), cert: readFileSync(certFile) };
const agent = new http.Agent({ keepAlive: true, maxSockets: 256 });
const HOP = new Set(['connection', 'keep-alive', 'proxy-connection', 'transfer-encoding', 'upgrade']);

function pass(req, res) {
  const length = req.headers['content-length'];
  const up = http.request({
    host: '127.0.0.1', port: Number(upstream), path: req.url, method: req.method, agent,
    headers: { host: req.headers[':authority'] ?? req.headers.host ?? '', ...(length ? { 'content-length': length } : {}) },
  }, (answer) => {
    const headers = Object.fromEntries(Object.entries(answer.headers).filter(([k]) => !HOP.has(k)));
    res.writeHead(answer.statusCode, headers);
    answer.pipe(res);
  });
  up.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end(); });
  req.pipe(up);
}

const h2 = http2.createSecureServer({ ...tls, allowHTTP1: false }, pass);
const h1 = https.createServer({ ...tls, ALPNProtocols: ['http/1.1'] }, pass);
h2.listen(0, '127.0.0.1', () => h1.listen(0, '127.0.0.1', () => {
  process.stdout.write(`${h2.address().port} ${h1.address().port}\n`);
}));
