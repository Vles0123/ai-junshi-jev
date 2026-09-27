import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import douyin_flow as f


class DouyinTests(unittest.TestCase):
    def test_explicit_speakers_context_and_multiline(self):
        c=f.prepare('我：今天怎么样？\n对方：有点累\n刚刚才下课','朋友A','普通朋友')
        self.assertEqual(c.message,'有点累\n刚刚才下课')
        self.assertIn('我: 今天怎么样？',c.context)
        self.assertIn('普通朋友',c.context)
        self.assertNotIn('刚刚才下课',c.context)

    def test_unreviewed_text_rejected(self):
        for raw in ('','你好','[待确认] 昵称','对方：你好\n[待确认] 时间','我：','me: hi'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):f.prepare(raw)

    def test_last_message_cannot_be_own(self):
        with self.assertRaisesRegex(ValueError,'最后一条'):f.prepare('对方：在吗\n我：在')

    def test_english_role_and_ascii_colon(self):
        c=f.prepare('Me: hi\nthem: hello')
        self.assertEqual(c.message,'hello')
        self.assertIn('我: hi',c.context)

    def test_bounds_keep_target_and_recent_messages(self):
        text='\n'.join('我：'+'甲'*200 for _ in range(80))+'\n对方：最后一句'
        c=f.prepare(text)
        self.assertLessEqual(len(c.context)+len(c.message),8192)
        self.assertEqual(c.message,'最后一句')
        with self.assertRaises(ValueError):f.prepare('对方：'+'甲'*4001)
        with self.assertRaises(ValueError):f.prepare('对方：你好',background='a'*1201)

    def test_spatial_labels_and_unknown_never_dropped(self):
        b=lambda text,x,y,w:SimpleNamespace(text=text,x=x,y=y,w=w,h=.03)
        text=f.ocr_draft([b('右侧回复',.65,.5,.25),b('对方消息',.08,.8,.25),b('居中昵称',.4,.9,.2)])
        self.assertEqual(text.splitlines(),['[待确认] 居中昵称','对方：对方消息','我：右侧回复'])
        with self.assertRaises(ValueError):f.prepare(text)

    def test_coordinate_conversion_primary_and_secondary(self):
        self.assertEqual(f.capture_rect((0,0),(100,200,300,100),900),(100,600,300,100))
        self.assertEqual(f.capture_rect((-1440,200),(0,500,300,100),900),(-1440,100,300,100))
        with self.assertRaises(ValueError):f.capture_rect((0,0),(0,0,10,10),900)

    def test_stale_request_generation_is_invalid(self):
        r=f.Revision();old=r.next();r.next()
        self.assertFalse(r.current(old))
        self.assertTrue(r.current(r.value))

    def fixtures(self):
        judge=Mock();judge.judge.return_value={'intent':'寻求共情','confidence':.6,'risk':2,'actions':['倾听']}
        generator=Mock();generator.generate.return_value={'groups':[
            {'tone':'自然关心','texts':['甲']},{'tone':'简洁直接','texts':['乙']},{'tone':'温和确认','texts':['丙']}]}
        judge.rank_candidates.return_value=[{'text':'乙','prob':.6},{'text':'甲','prob':.3},{'text':'丙','prob':.1}]
        return judge,generator

    def test_full_flow_uses_same_reviewed_context_and_ranks(self):
        j,g=self.fixtures();c=f.prepare('我：怎么了\n对方：有点难过')
        result=f.analyze(c,j,g)
        self.assertEqual([x['text'] for x in result['candidates']],['乙','甲','丙'])
        self.assertEqual(j.judge.call_args.kwargs['context'],c.context)
        self.assertEqual(g.generate.call_args.kwargs['context'],c.context)
        self.assertEqual(j.rank_candidates.call_args.kwargs['context'],c.context)
        self.assertEqual(result['candidates'][0]['tone'],'简洁直接')

    def test_judgment_failure_never_fabricates_replies(self):
        j,g=self.fixtures();j.judge.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):f.analyze(f.prepare('对方：你好'),j,g)
        g.generate.assert_not_called()

    def test_ranking_failure_keeps_unscored_replies(self):
        j,g=self.fixtures();j.rank_candidates.side_effect=ValueError()
        result=f.analyze(f.prepare('对方：你好'),j,g)
        self.assertEqual(len(result['candidates']),3)
        self.assertTrue(all(c['prob'] is None for c in result['candidates']))
        self.assertIn('原顺序',result['warning'])

    def test_incomplete_ranking_never_discards_generated_replies(self):
        for rows in ([], [{'text':'甲','prob':1}], [{'text':'甲','prob':1}]*3,
                     [{'text':'不存在','prob':1}]*3, None):
            with self.subTest(rows=rows):
                j,g=self.fixtures();j.rank_candidates.return_value=rows
                result=f.analyze(f.prepare('对方：你好'),j,g)
                self.assertEqual([x['text'] for x in result['candidates']],['甲','乙','丙'])
                self.assertTrue(all(x['prob'] is None for x in result['candidates']))

    def test_empty_generation_keeps_valid_judgment(self):
        j,g=self.fixtures();g.generate.return_value={'groups':[],'error':'failure'}
        result=f.analyze(f.prepare('对方：你好'),j,g)
        self.assertEqual(result['verdict']['intent'],'寻求共情')
        self.assertEqual(result['candidates'],[])
        self.assertIn('生成失败',result['warning']);j.rank_candidates.assert_not_called()

    def test_duplicate_candidates_not_invented(self):
        j,g=self.fixtures();g.generate.return_value={'groups':[{'tone':x,'texts':['同一句']} for x in f.TONES]}
        result=f.analyze(f.prepare('对方：你好'),j,g)
        self.assertEqual(len(result['candidates']),1);j.rank_candidates.assert_not_called()

    def test_closed_panel_ignores_inflight_result_before_touching_ui(self):
        import ast
        path=Path(__file__).resolve().parents[1]/'src/douyin_panel.py'
        tree=ast.parse(path.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='applyResult_')
        scope={};exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'panel','exec'),scope)
        r=f.Revision();old=r.next();r.next()
        panel=SimpleNamespace(revision=r)
        scope['applyResult_'](panel,{'token':old,'kind':'analysis'})

if __name__=='__main__':unittest.main()
