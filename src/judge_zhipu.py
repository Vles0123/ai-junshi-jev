"""GLM analysis through the account endpoint selected by the user."""
import userconfig
from judge_openrouter import OpenRouterJudge
class ZhipuJudge(OpenRouterJudge):
    backend_label='智谱 GLM（候选保持原顺序）'
    result_label='智谱 GLM · 模型估计'
    def credentials(self):
        base=userconfig.get('ZHIPU_BASE_URL')
        key=userconfig.get('ZHIPU_API_KEY')
        model=userconfig.get('ZHIPU_MODEL') or 'glm-5.3'
        if base not in ('https://open.bigmodel.cn/api/coding/paas/v4','https://open.bigmodel.cn/api/paas/v4') or not key:
            raise ValueError('智谱接口或密钥未配置')
        return base,key,model
    def parameters(self,schema):
        return {'thinking':{'type':'enabled'},'reasoning_effort':'low',
                'max_tokens':4096,'response_format':{'type':'json_object'}}
