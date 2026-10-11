import test from 'node:test';
import assert from 'node:assert/strict';
import extension from '../extensions/pcbagent.ts';

function harness(exec = async () => ({code: 0, stdout: '{}', stderr: ''})) {
  const hooks = {}, messages = [], tools = {};
  extension({ on: (name, fn) => { hooks[name] = fn; }, registerProvider(){},
    registerTool: tool => { tools[tool.name] = tool; }, exec,
    sendMessage: (message, options) => messages.push({message, options}) });
  const controller = new AbortController();
  const ctx = { cwd: '.', model: {api: 'some-other-provider'}, signal: controller.signal,
    abort() { assert.fail('The extension must never abort automatically'); } };
  return {hooks, messages, tools, controller, ctx};
}

test('old deadlines, repeated errors and many requests never cancel or cap payloads', async () => {
  const keys = ['PCB_MODEL_TIMEOUT_S','PCB_EPISODE_TIMEOUT_S','PCB_MAX_MODEL_CALLS','PCB_REPAIR_ATTEMPTS'];
  const old = keys.map(key => process.env[key]);
  try {
    for (const key of keys) process.env[key] = '0.001';
    const {hooks,ctx} = harness();
    hooks.before_agent_start({systemPrompt: 'base'}, ctx);
    assert.equal(hooks.tool_call, undefined);
    assert.equal(hooks.turn_end, undefined);
    const payload = {max_tokens: 32000};
    for (let i = 0; i < 100; i++) {
      assert.equal(hooks.before_provider_request({payload}, ctx), undefined);
      assert.equal(hooks.tool_result({toolName:'bash', toolCallId:String(i), input:{command:'verify'},
        isError:true, content:[{type:'text',text:'failed'}]}, ctx), undefined);
    }
    assert.deepEqual(payload, {max_tokens:32000});
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.equal(ctx.signal.aborted, false);
  } finally {
    keys.forEach((key,i) => old[i] === undefined ? delete process.env[key] : process.env[key] = old[i]);
  }
});

test('truncated responses continue without executing partial tool calls', () => {
  const {hooks,messages,ctx} = harness();
  const event = {message: {role:'assistant',model:'test',stopReason:'length',content:[
    {type:'toolCall',id:'partial'}, {type:'text',text:'partial answer'}]}};
  const result = hooks.message_end(event, ctx);
  assert.equal(result.message.stopReason, 'stop');
  assert.deepEqual(result.message.content, [{type:'text',text:'partial answer'}]);
  assert.deepEqual(messages[0].options, {triggerTurn:true,deliverAs:'followUp'});
});

test('manual cancellation suppresses continuation', () => {
  const {hooks,messages,controller,ctx} = harness();
  controller.abort();
  assert.equal(hooks.message_end({message: {role:'assistant',model:'test',stopReason:'length',content:[]}}, ctx), undefined);
  assert.equal(messages.length, 0);
});

test('a failed stage is reported and does not cancel the session', async () => {
  const {tools, ctx} = harness(async () => ({code: 1, stdout: '{"status":"unmet_requirement"}', stderr: ''}));
  const result = await tools.pcb_stage.execute('id', {design:'designs/test', stage:'verify'}, ctx.signal);
  assert.equal(result.content[0].text, '{"status":"unmet_requirement"}');
  assert.equal(ctx.signal.aborted, false);
});

test('stage execution forwards user cancellation without an injected timeout', async () => {
  let options;
  const {tools,controller} = harness(async (_command, _args, opts) => {
    options = opts;
    return new Promise((resolve, reject) => opts.signal.addEventListener('abort', () => reject(new Error('user cancelled')), {once:true}));
  });
  const result = tools.pcb_stage.execute('id', {design:'designs/test',stage:'verify'}, controller.signal);
  assert.equal(options.signal, controller.signal);
  assert.equal('timeout' in options, false);
  controller.abort();
  await assert.rejects(result, /user cancelled/);
});
