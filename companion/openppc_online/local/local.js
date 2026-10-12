/* Only in the copy of the app that `openppc-online app` serves from this computer: that server writes a token into
   the page, and this asks it what it is. openppc.si never loads this file. */
(() => {
  const token = document.querySelector('meta[name="openppc-local"]')?.getAttribute('content') || '';
  if (!token) return;
  fetch('/api/info', { headers: { 'X-OpenPPC-Token': token } })
    .then((res) => res.json())
    .then((info) => {
      if (!info.ok) return;
      document.documentElement.dataset.local = 'on';
      const line = document.querySelector('.privacy-long');
      if (line) line.textContent += ` · openppc-online ${info.version}`;
    })
    .catch(() => {});  // the server stopped: the app still runs in this tab
})();
