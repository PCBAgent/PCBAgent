import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import { appendFileSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');

export default function (pi: ExtensionAPI) {
  let requestStarted = 0;
  let calls = 0;
  const logDir = join(repo, '.agent');
  mkdirSync(logDir, { recursive: true });
  const log = (event: object) => appendFileSync(join(logDir, 'runtime.jsonl'), JSON.stringify({ at: new Date().toISOString(), ...event }) + '\n');
  pi.on('before_agent_start', (event) => {
    calls = 0;
    const prompt = readFileSync(join(repo, 'agent/system-prompt.md'), 'utf8');
    return { systemPrompt: prompt + '\n\n' + event.systemPrompt,
      message: { customType: 'pcb-stage-context', display: false,
        content: `Use pcb_stage(design, stage) for prepare → verify → parts → netlist. Generate skidl_sim.py after prepare and skidl_kicad.py after parts. Relevant instructions: skills/pcb-agent/SKILL.md; skills/{requirements,circuit,parts,skidl,layout}/SKILL.md. Schemas: skills/circuit/schemas/. Existing artifacts: designs/<slug>/{design,parts,layout}/. Only the user cancels execution. There are no automatic request, session or repair limits. Diagnose failures and continue working; report engineering checks honestly.` } };
  });
  pi.on('before_provider_request', () => {
    requestStarted = Date.now();
    calls++;
    // Observe requests without modifying provider payloads or cancellation.
  });
  pi.on('message_end', (event, ctx) => {
    if (event.message.role !== 'assistant') return;
    const message = event.message;
    log({ event: 'model_response', elapsed_ms: Date.now()-requestStarted, model: message.model,
      stop_reason: message.stopReason, usage: message.usage, call: calls });
    if (message.stopReason === 'length' && !ctx.signal?.aborted) {
      // Continue after provider truncation without executing incomplete arguments.
      pi.sendMessage({ customType: 'pcb-continue', display: false,
        content: 'The provider truncated the last response. Its tool calls were discarded and did not execute. Continue the task using smaller, complete tool calls. Inspect files before continuing a partial edit. Do not stop because of response length.' },
        { triggerTurn: true, deliverAs: 'followUp' });
      return { message: { ...message, content: message.content.filter(c => c.type !== 'toolCall'), stopReason: 'stop' } };
    }
  });
  pi.on('tool_result', (event) => {
    // Compact execution output only. Reads retain the exact requested source text.
    if (event.toolName !== 'bash' && event.toolName !== 'pcb_stage') return;
    const full = event.content.filter(c => c.type === 'text').map(c => c.text).join('\n');
    if (full.length <= 6000) return;
    const path = join(logDir, `tool-${Date.now()}-${event.toolCallId.replace(/[^a-zA-Z0-9_-]/g, '_')}.log`);
    appendFileSync(path, full);
    const lines = [...new Set(full.split('\n'))];
    return { content: [{ type: 'text', text: lines.join('\n').slice(-5500) + `\nFull output: ${path}` }] };
  });
  pi.registerTool({ name: 'pcb_stage', label: 'PCB stage', description: 'Run one deterministic PCB stage without automatic timeouts and return a compact result with log path. Never places or routes.',
    parameters: { type: 'object', properties: { design: { type: 'string', description: 'Existing designs/<slug> directory' },
      stage: { type: 'string', enum: ['prepare', 'verify', 'parts', 'netlist'] } }, required: ['design', 'stage'], additionalProperties: false } as any,
    async execute(_id, params: any, signal) {
      const result = await pi.exec(join(repo, '.venv/bin/python'), [join(repo, 'tools/pcb_stage.py'), params.design, params.stage], { signal });
      if (signal?.aborted) throw new Error('Cancelled');
      const text = result.stdout || result.stderr || '';
      return { content: [{ type: 'text', text }], details: { stage: params.stage, exitCode: result.code } };
    }
  });
  pi.registerProvider('pcb-ollama', { api: 'openai-completions', baseUrl: process.env.PCB_OLLAMA_BRIDGE_URL || 'http://127.0.0.1:8766/v1', apiKey: 'local',
    models: [{ id: process.env.PCB_OLLAMA_MODEL || 'nemotron3:33b', name: 'PCB local model (native Ollama)', reasoning: true, input: ['text'],
      contextWindow: Number(process.env.PCB_CONTEXT_WINDOW || 32768), maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, compat: { supportsDeveloperRole: false, supportsReasoningEffort: true } }] });
}
