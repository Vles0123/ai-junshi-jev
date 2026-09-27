import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import insight

class InsightTests(unittest.TestCase):
    def test_reminder_is_not_a_memory_question(self):
        self.assertIn('字面', insight.reading_question('明天下午三点开会，记得带上方案。'))
        self.assertIn('记忆', insight.reading_question('你还记得吗？'))

    def test_context_uncertainty_is_available(self):
        questions=insight.questions('那你说。')
        self.assertIn('信息不足',questions[1][2])
        self.assertIn('上下文不足',questions[0][2])

    def test_remainder_is_shown_without_renormalizing_top_three(self):
        text=insight.distribution_lines({'一':.4,'二':.3,'三':.2,'四':.1})
        self.assertIn('一  40%',text)
        self.assertIn('其他可能  10%',text)

    def test_no_fabricated_missing_scores(self):
        self.assertEqual(insight.distribution_lines({}), '尚无可用评分')
        self.assertEqual(insight.distribution_lines({'坏':float('nan'),'越界':2}), '尚无可用评分')
        sections=insight.card_sections({'message':'好','actions':['先核实记录']})
        self.assertEqual(sections[3], '先核实记录')

    def test_estimates_are_not_rounded_to_certainty(self):
        # Retain explicit alternatives even when their rounded percentage is small.
        text=insight.distribution_lines({'是':.93,'不是':.07})
        self.assertIn('不是  7%',text)

if __name__=='__main__': unittest.main()
