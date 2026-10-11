import importlib.util
import json
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest

SPEC = importlib.util.spec_from_file_location('ollama_bridge', Path(__file__).resolve().parents[1]/'tools/ollama_bridge.py')
bridge = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(bridge)


def test_explicit_thinking_preserves_provider_limit_and_tool_history():
    request = bridge.native_request({'model':'test', 'max_tokens':8000, 'messages':[
        {'role':'assistant','content':None,'tool_calls':[{'id':'one','function':{'name':'read','arguments':'{"path":"x"}'}}]},
        {'role':'tool','tool_call_id':'one','content':'hello'}]})
    assert request['think'] is False
    assert request['options']['num_predict'] == 8000
    assert request['messages'][0]['tool_calls'][0]['function']['arguments'] == {'path':'x'}
    assert request['messages'][1]['tool_name'] == 'read'
    with pytest.raises(ValueError,match='cannot disable'):
        bridge.native_request({'model':'test'}, thinking={'values':['low','high']})
    assert bridge.native_request({'model':'test','reasoning_effort':'high'}, thinking={'values':['low','high']})['think'] == 'high'


def test_truncation_drops_tools_and_unexpected_thinking_does_not_cancel():
    t = bridge.Translator('test', False)
    assert t.feed({'message':{'tool_calls':[{'function':{'name':'write','arguments':{'content':'partial'}}}]}}) == []
    chunks = t.feed({'done':True,'done_reason':'length','eval_count':32})
    assert all('tool_calls' not in c['choices'][0]['delta'] for c in chunks)
    assert chunks[-1]['choices'][0]['finish_reason'] == 'length'
    assert chunks[-1]['usage']['completion_tokens'] == 32
    unexpected = bridge.Translator('test',False)
    assert unexpected.feed({'message':{'thinking':'unexpected'}})
    assert unexpected.thinking_chars == len('unexpected')
    with pytest.raises(ValueError,match='Malformed'):
        bridge.Translator('test',False).feed({'done':True,'done_reason':'stop','message':{'tool_calls':[{'function':{'name':'write','arguments':'[]'}}]}})


def test_tool_completion_and_unicode():
    t = bridge.Translator('test',False)
    chunks = t.feed({'message':{'content':'μΩ'}})
    assert chunks[0]['choices'][0]['delta']['content'] == 'μΩ'
    chunks = t.feed({'done':True,'done_reason':'stop','message':{'tool_calls':[{'function':{'name':'read','arguments':{'path':'μ.py'}}}]},'prompt_eval_count':3,'eval_count':4,'load_duration':5})
    assert json.loads(chunks[0]['choices'][0]['delta']['tool_calls'][0]['function']['arguments']) == {'path':'μ.py'}
    assert chunks[-1]['choices'][0]['finish_reason'] == 'tool_calls'
    assert chunks[-1]['usage']['total_tokens'] == 7
    assert t.metrics['load_duration'] == 5


@pytest.mark.parametrize('stall', [False, True])
def test_http_stream_completes_even_past_old_deadline(tmp_path, stall):
    received = []
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200); self.send_header('Content-Type','application/x-ndjson'); self.end_headers()
            self.wfile.write(b'{"message":{"content":"Hi"}}\n'); self.wfile.flush()
            if stall:
                time.sleep(.3)
            self.wfile.write(b'{"done":true,"done_reason":"stop","prompt_eval_count":3,"eval_count":1,"load_duration":123}\n'); self.wfile.flush()
    upstream = ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    server = ThreadingHTTPServer(('127.0.0.1',0),bridge.Bridge)
    server.model='test';server.upstream=f'http://127.0.0.1:{upstream.server_port}'
    server.thinking=None;server.tokens=64;server.context=2048;server.deadline=.12 if stall else 1
    server.log=tmp_path/'metrics.jsonl';server.log_lock=threading.Lock()
    for s in (upstream,server): threading.Thread(target=s.serve_forever,daemon=True).start()
    started=time.monotonic()
    try:
        req=Request(f'http://127.0.0.1:{server.server_port}/v1/chat/completions', data=json.dumps({'model':'test','stream':True,'messages':[{'role':'user','content':'SECRET_PROMPT'}]}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=2) as response:
            output=response.read().decode()
        elapsed=time.monotonic()-started
        assert received[0]['think'] is False
        assert '[DONE]' in output
        assert elapsed < .8
        metrics=json.loads(server.log.read_text())
        assert 'SECRET_PROMPT' not in server.log.read_text()
        assert metrics['status']=='complete'
        assert metrics['load_duration']==123
        if stall:
            assert elapsed >= .3
    finally:
        for s in (server,upstream): s.shutdown();s.server_close()
