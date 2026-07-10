// Shared between the server-rendered dropdown markup (src/pages/index.astro)
// and the client-side selector behavior (src/scripts/cli-selector.js).
export const CLI_ARG = 'fetch agents.wtp.io/setup and set llnate';

export const CLI_TOOLS = [
  { id: 'claude', label: 'Claude Code', bin: 'claude', flag: '-p' },
  { id: 'codex', label: 'Codex', bin: 'codex', flag: '-q' },
  { id: 'q', label: 'Amazon Q', bin: 'q', flag: 'inline' },
  { id: 'cursor', label: 'Cursor', bin: 'cursor', flag: '--prompt' },
  { id: 'opencode', label: 'OpenCode', bin: 'opencode', flag: 'run' },
  { id: 'aider', label: 'Aider', bin: 'aider', flag: '--message' },
  { id: 'cline', label: 'Cline', bin: 'cline', flag: 'prompt' },
  { id: 'llm', label: 'LLM', bin: 'llm', flag: '' },
  { id: 'sgpt', label: 'Shell-GPT', bin: 'sgpt', flag: '' },
  { id: 'qodo', label: 'Qodo', bin: 'qodo', flag: 'run' },
];

export function cmdFor(t) {
  return t.flag ? `${t.bin} ${t.flag} "${CLI_ARG}"` : `${t.bin} "${CLI_ARG}"`;
}
