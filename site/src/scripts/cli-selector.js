// Hero "pick your CLI" dropdown: swaps the displayed command and the copy
// button's payload between agent CLIs, ported from the mockup's TOOLS list.
import { CLI_TOOLS, cmdFor } from '../data/cli-tools.js';

export function initCliSelector() {
  const root = document.getElementById('cli-selector');
  if (!root) return;

  const toggle = document.getElementById('cli-toggle');
  const menu = document.getElementById('cli-menu');
  const toolLabelEl = document.getElementById('cli-tool-label');
  const binEl = document.getElementById('cli-bin');
  const flagEl = document.getElementById('cli-flag');
  const copyBtn = document.getElementById('cli-copy');

  function render(t) {
    toolLabelEl.textContent = t.label;
    binEl.textContent = t.bin;
    flagEl.textContent = t.flag;
    flagEl.hidden = !t.flag;
    copyBtn.setAttribute('data-copy', cmdFor(t));
    menu.querySelectorAll('.ll-cli-item').forEach((item) => {
      const dot = item.querySelector('[data-active-dot]');
      if (dot) dot.style.visibility = item.dataset.toolId === t.id ? 'visible' : 'hidden';
    });
  }

  render(CLI_TOOLS[0]);

  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.classList.toggle('is-open');
  });

  menu.querySelectorAll('.ll-cli-item').forEach((item) => {
    item.addEventListener('click', () => {
      const t = CLI_TOOLS.find((x) => x.id === item.dataset.toolId);
      if (t) render(t);
      menu.classList.remove('is-open');
    });
  });

  document.addEventListener('mousedown', (e) => {
    if (menu.classList.contains('is-open') && !root.contains(e.target)) {
      menu.classList.remove('is-open');
    }
  });
}
