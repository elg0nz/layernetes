// Generic "copy to clipboard, flash a confirmation" behavior for any button
// carrying data-copy="<text>" and an optional [data-copy-label] child that
// gets un-hidden for ~1.6s after a successful copy.
export function initCopyButtons(root = document) {
  root.querySelectorAll('[data-copy]').forEach((btn) => {
    const label = btn.querySelector('[data-copy-label]');
    let timer;
    btn.addEventListener('click', async () => {
      const text = btn.getAttribute('data-copy') || '';
      try {
        if (navigator.clipboard) await navigator.clipboard.writeText(text);
        window.posthog?.capture('command_copied', { snippet: text.slice(0, 120) });
      } catch (e) {
        // clipboard permissions denied — nothing actionable to do here
      }
      if (label) {
        label.hidden = false;
        clearTimeout(timer);
        timer = setTimeout(() => {
          label.hidden = true;
        }, 1600);
      }
    });
  });
}
