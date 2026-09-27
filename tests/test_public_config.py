import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import generate
import settings_config
from vles_bootstrap import DEFAULT_CONFIG

class PublicConfigTests(unittest.TestCase):
    def test_public_default_enables_timeline_without_key(self):
        self.assertIn('JUDGE_BACKEND=zhipu', DEFAULT_CONFIG)
        self.assertIn('WECHAT_READ_MODE=ax', DEFAULT_CONFIG)
        self.assertIn("ZHIPU_API_KEY=''", DEFAULT_CONFIG)
        self.assertNotIn('/coding/', DEFAULT_CONFIG)

    def test_zhipu_used_for_generation_without_separate_provider(self):
        def provider(prefix):
            return {'key': 'synthetic-key' if prefix == 'ZHIPU' else '', 'base': '', 'model': '', 'source': 'test'}
        with patch('userconfig.provider', side_effect=provider):
            self.assertEqual(generate.load_credentials(), ('https://open.bigmodel.cn/api/paas/v4', 'synthetic-key', 'glm-5.3', 'test', 'openai'))

    def test_zhipu_probe_has_sufficient_output_budget(self):
        with patch('settings_config.http_post_json', return_value={'choices':[{'message':{'content':'连接成功'}}]}) as call:
            settings_config.test_connection('ZHIPU', 'https://open.bigmodel.cn/api/paas/v4', 'synthetic-key', 'glm-5.3')
        self.assertEqual(call.call_args.args[2]['max_tokens'], 4096)
