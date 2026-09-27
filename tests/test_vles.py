import copy
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import builtin
import chat_judgment as rubric
import judge
import judge_jev
import generate
import userconfig
from vles_bootstrap import seed


def good():
    return {'answers': {'intent': {'choice': '上下文不足', 'confidence': 0.51}, 'risk': {'score': 3.2}}}


class DecisionTests(unittest.TestCase):
    def test_valid_and_zero(self):
        for confidence in (0, 0.51, 1):
            x = good(); x['answers']['intent']['confidence'] = confidence
            self.assertEqual(rubric.parse_answers(x)['confidence'], confidence)

    def test_missing_scores_are_not_safe(self):
        for x in ({}, {'answers': {}}, {'answers': {'intent': {'choice': '轻松聊天'}}}):
            with self.subTest(x=x), self.assertRaises(ValueError):
                rubric.parse_answers(x)

    def test_unknown_label(self):
        x = good(); x['answers']['intent']['choice'] = '读心成功'
        with self.assertRaises(ValueError): rubric.parse_answers(x)

    def test_reject_invalid_numbers(self):
        for field in ('confidence', 'score'):
            for v in (None, True, -1, float('nan'), float('inf'), '0.9', 10):
                x = good(); section = 'intent' if field == 'confidence' else 'risk'
                x['answers'][section][field] = v
                with self.subTest(field=field, value=v), self.assertRaises(ValueError):
                    rubric.parse_answers(x)

    def test_probability_used_when_confidence_missing(self):
        x=good(); del x['answers']['intent']['confidence']
        x['answers']['intent']['probabilities']={'上下文不足': 0.4}
        self.assertEqual(rubric.parse_answers(x)['confidence'], 0.4)

    def test_payload_and_endpoint(self):
        for base, endpoint in [('https://api.typesafe.ai','https://api.typesafe.ai/v1/systemone'),('https://openrouter.ai/api/alpha/decisions','https://openrouter.ai/api/alpha/decisions')]:
            j=judge_jev.JevJudge(base=base,key='test-only',model='jev-latest')
            with patch.object(judge_jev,'http_post_json',return_value=good()) as post:
                result=j.judge('你今天是不是忘了？','背景：普通朋友')
            args=post.call_args.args
            self.assertEqual(args[0],endpoint)
            self.assertIn('普通朋友',args[2]['state'])
            self.assertIn('上下文不足',args[2]['questions']['intent']['criteria'])
            self.assertEqual(result['intent'],'上下文不足')
            self.assertIsNone(j.load_status)

    def test_api_error_propagates_without_local_fallback(self):
        with patch.object(judge_jev,'jev_configured',return_value=True):
            j=judge.make_judge()
        with patch.object(j,'_post',side_effect=TimeoutError), self.assertRaises(TimeoutError):
            j.judge('你好')

    def test_missing_key_fails_before_network(self):
        j=judge_jev.JevJudge(key='test-only');j.key=''
        with patch.object(judge_jev,'http_post_json') as post, self.assertRaisesRegex(ValueError,'密钥'):
            j.judge('你好')
        post.assert_not_called()

    def test_ranking_missing_score_not_zero(self):
        j=judge_jev.JevJudge(key='test-only')
        with patch.object(j,'_post',return_value={'answers':{'best':{'choice':'reply_1','confidence':0.7}}}):
            rows=j.rank_candidates('你好','轻松聊天',['你好呀','最近如何'])
        self.assertEqual(rows[0]['text'],'最近如何')
        self.assertEqual(rows[0]['prob'],0.7)
        self.assertIsNone(rows[1]['prob'])

    def test_ranking_invalid_choice_rejected(self):
        j=judge_jev.JevJudge(key='test-only')
        with patch.object(j,'_post',return_value={'answers':{'best':{'choice':'fake'}}}), self.assertRaises(ValueError):
            j.rank_candidates('你好','轻松聊天',['a','b'])

    def test_no_bundled_credentials(self):
        self.assertEqual(builtin.API_KEY,'')
        self.assertEqual(builtin.BASE_URL,'')
        with patch.object(userconfig,'provider',return_value={'key':'','base':'','model':'','source':'none'}):
            self.assertEqual(generate.load_credentials()[1],'')

    def test_seed_private_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'settings/env'
            self.assertTrue(seed(p))
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            self.assertIn('JUDGE_BACKEND=zhipu',p.read_text())
            p.write_text('keep-existing')
            self.assertFalse(seed(p))
            self.assertEqual(p.read_text(),'keep-existing')


    def test_hud_unscored_candidate_does_not_crash(self):
        import ast
        import threading
        from types import SimpleNamespace
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'src/hud.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='HudController')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_rank_payload')
        method.decorator_list=[]
        scope={'chat_context':SimpleNamespace(model_message=lambda text,ctx:text)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])), 'hud_rank', 'exec'),scope)
        fake=SimpleNamespace(_model_lock=threading.Lock(),_reply_current=lambda:True,
            _reply_worker=SimpleNamespace(),_active_context=None,
            judge=SimpleNamespace(rank_candidates=lambda *a,**kw:[{'text':'甲','prob':None},{'text':'乙','prob':0.7}]))
        result=scope['_rank_payload'](fake,[(0,'自然关心',[{'text':'甲'},{'text':'乙'}])],'消息','寻求帮助')
        self.assertEqual(result[0][2][0],{'text':'乙','prob':0.7})
        self.assertIsNone(result[0][2][1]['prob'])

    def test_real_transport_to_local_fake_service(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append((self.path,body))
                result=good() if 'intent' in body['questions'] else {'answers':{'best':{'choice':'reply_0','confidence':0.6,'probabilities':{'reply_0':0.6,'reply_1':0.4}}}}
                raw=json.dumps(result).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            j=judge_jev.JevJudge(base=f'http://127.0.0.1:{server.server_port}',key='synthetic-only')
            self.assertEqual(j.judge('合成消息')['intent'],'上下文不足')
            rows=j.rank_candidates('合成消息','上下文不足',['候选甲','候选乙'])
            self.assertEqual([r['prob'] for r in rows],[0.6,0.4])
            self.assertEqual([r[0] for r in received],['/v1/systemone']*2)
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__': unittest.main()
