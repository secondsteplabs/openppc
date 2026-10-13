// SPDX-License-Identifier: MIT
import { inspect } from './inspect.js';
import { render, renderError } from './view.js';

const PATIENCE = 5000; // ms; a page whose main thread is stuck never answers

async function main() {
  const root = document.getElementById('report');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const signatures = await (await fetch(chrome.runtime.getURL('signatures.json'))).json();
    const late = new Promise((_, fail) => { setTimeout(() => fail(new Error('late')), PATIENCE); });
    render(root, await Promise.race([inspect(tab.id), late]), signatures);
  } catch (e) {
    renderError(root, e instanceof Error && e.message === 'late');
  }
}

void main();
