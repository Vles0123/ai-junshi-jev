"""Conversation cards backed by actual model distributions, never invented scores."""
import math
from chat_judgment import INTENTS, INSTRUCTIONS

ACTION_OPTIONS = {
    "先核实聊天记录": "对方在问过去的约定或事实，先查看已有记录，不编造记忆。",
    "先回应对方感受": "先承认对方明确表达的情绪，真诚回应关注或失望。",
    "直接回答具体问题": "信息充分、问题明确时，直接给出真实答案。",
    "温和确认对方意思": "存在歧义或上下文不足，先问清具体指什么。",
    "给出具体安排": "明确自己能做的事情、下一步或时间，不作虚假承诺。",
    "尊重边界，稍后再聊": "对方明确要求暂停、拒绝或独处，给对方空间。",
}


def reading_question(message):
    if any(s in message for s in ("忘", "记不记", "说过", "告诉过")) or ("记得" in message and any(q in message for q in ("吗", "？", "?"))):
        return "对方主要是在核对记忆或事实吗？"
    if any(s in message for s in ("那你说", "你说说", "说来听")):
        return "现在适合直接给出确定答案吗？"
    if "最好是" in message:
        return "这句话是在明确表达相信吗？"
    return "只按字面理解这句话，是否足够？"


def questions(message):
    return [
        ("intent", "最可能的沟通需求是什么？" + INSTRUCTIONS, INTENTS),
        ("reading", reading_question(message), {
            "是": "现有上下文支持肯定判断。",
            "不是": "现有上下文支持否定判断。",
            "信息不足": "无法确定，不把反问或短句自动当成隐藏动机。"}),
        ("action", "现在最合适的第一步是什么？根据可见内容选择，不猜测未展示的聊天记录。", ACTION_OPTIONS),
    ]


def distribution_lines(probs, limit=3):
    values = [(str(k), float(v)) for k, v in (probs or {}).items()
              if isinstance(v, (int, float)) and not isinstance(v, bool)
              and math.isfinite(v) and 0 <= v <= 1]
    values.sort(key=lambda kv: -kv[1])
    if not values:
        return "尚无可用评分"
    shown=values[:limit]
    lines=[f"{label}  {value:.0%}" for label, value in shown]
    if len(values) > limit:
        rest=sum(v for _, v in values[limit:])
        if rest >= .005:
            lines.append(f"其他可能  {rest:.0%}")
    return "\n".join(lines)


def card_sections(verdict):
    question=verdict.get("reading_question") or reading_question(verdict.get("message", ""))
    reading=distribution_lines(verdict.get("reading_probs"))
    intent=distribution_lines(verdict.get("intent_probs"))
    actions=distribution_lines(verdict.get("action_probs")) if verdict.get("action_probs") else " · ".join(verdict.get("actions", []))
    return question, reading, intent, actions
