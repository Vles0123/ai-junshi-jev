"""Pure, testable Douyin screenshot-review-analysis flow. No automatic upload."""
from __future__ import annotations
from dataclasses import dataclass
import re
from chat_context import context_text

MAX_INPUT = 24000
TONES = ['自然关心', '简洁直接', '温和确认']
ROLE = re.compile(r'^(我|对方|me|them)\s*[:：]\s*(.*)$', re.I)


@dataclass(frozen=True)
class Conversation:
    message: str
    context: str
    contact: str


class Revision:
    def __init__(self): self.value = 0
    def next(self):
        self.value += 1
        return self.value
    def current(self, token): return token == self.value


def prepare(text: str, contact: str = '', background: str = '') -> Conversation:
    if not text.strip(): raise ValueError('先导入截图或粘贴聊天文字。')
    if len(text) > MAX_INPUT: raise ValueError('内容过长，请保留最近的对话（最多 24000 字符）。')
    if len(background) > 1200: raise ValueError('关系背景请控制在 1200 字符内。')
    if len(contact) > 100: raise ValueError('会话备注请控制在 100 字符内。')
    messages = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line: continue
        if line.startswith('[待确认]'):
            raise ValueError(f'第 {i} 行还未确认归属，请改成“我：”或“对方：”，或删除非消息文字。')
        match = ROLE.match(line)
        if not match:
            if not messages: raise ValueError('每条消息以“我：”或“对方：”开头。多行消息可在下一行续写。')
            old = messages[-1]
            messages[-1] = (old[0]+'\n'+line, old[1], old[2])
            continue
        who, body = match.groups()
        if not body: raise ValueError(f'第 {i} 行没有消息内容。')
        mine = who.lower() in ('我','me')
        messages.append((body, 'me' if mine else 'them', '我' if mine else '对方'))
    if not messages: raise ValueError('没有可分析的聊天消息。')
    if messages[-1][1] != 'them':
        raise ValueError('最后一条是我方消息。请保留到这次要回复的对方消息为止。')
    message = messages[-1][0]
    if len(message) > 4000: raise ValueError('最后一条消息太长，请缩短到 4000 字符内。')
    header = '来源：抖音私信；以下是用户校对的文字。\n'
    if contact.strip(): header += '会话备注：'+contact.strip()+'\n'
    if background.strip(): header += '关系背景：'+background.strip()
    ctx = context_text(messages, len(messages)-1, limit=30, background=header)
    return Conversation(message, ctx or '', contact.strip())


def ocr_draft(blocks):
    """Tentative spatial labels only; the user must review before sending to models."""
    rows=[]
    for b in sorted(blocks,key=lambda b:(-float(b.y),float(b.x))):
        text=str(b.text).strip()
        if not text: continue
        x,right=float(b.x),float(b.x+b.w)
        if x >= .52: side='我'
        elif right <= .48 or (x <= .18 and right < .85): side='对方'
        else: side='[待确认]'
        # Only join lines that look like one wrapped bubble, never leap over another speaker.
        top=1-float(b.y+b.h)
        if rows:
            prev=rows[-1]
            gap=top-prev['bottom']
            if side==prev['side'] and side!='[待确认]' and 0 <= gap <= min(.022,float(b.h)*.6) and abs(x-prev['x'])<.07:
                prev['text']+='\n'+text;prev['bottom']=1-float(b.y)
                continue
        rows.append({'side':side,'text':text,'x':x,'bottom':1-float(b.y)})
    return '\n'.join((r['side']+'：' if r['side']!='[待确认]' else '[待确认] ')+r['text'] for r in rows)


def capture_rect(screen_origin, local_rect, primary_height):
    """AppKit bottom-origin display points -> screencapture top-origin desktop rect."""
    sx,sy=screen_origin; x,y,w,h=local_rect
    if w<20 or h<20: raise ValueError('框选区域太小，请重新选择。')
    return round(sx+x),round(primary_height-(sy+y+h)),round(w),round(h)


def analyze(conversation, judge, generator):
    verdict=judge.judge(conversation.message, context=conversation.context)
    gen=generator.generate(conversation.message, intent=verdict['intent'], slot_tones=TONES, context=conversation.context)
    candidates=[]
    for group in gen.get('groups',[]):
        texts=group.get('texts') or []
        if texts and not any(c['text']==texts[0] for c in candidates):
            candidates.append({'text':texts[0],'tone':group['tone'],'prob':None})
    warning=''
    if not candidates:
        warning='判断完成，回复生成失败；请检查回复模型配置。'
    elif len(candidates)<3:
        warning=f'本次得到 {len(candidates)} 条不同回复，其余话术未生成或重复。'
    if len(candidates)>1:
        try:
            ranked=judge.rank_candidates(conversation.message,verdict['intent'],[c['text'] for c in candidates],context=conversation.context)
            index={c['text']:c for c in candidates}
            # Ranking is optional; never lose generated replies to empty/partial output.
            if not isinstance(ranked,list) or len(ranked)!=len(candidates):
                raise ValueError('incomplete ranking')
            ordered=[r['text'] for r in ranked]
            if len(set(ordered))!=len(index) or set(ordered)!=set(index):
                raise ValueError('invalid ranking')
            reordered=[dict(index[r['text']],prob=r.get('prob')) for r in ranked]
            candidates=reordered
        except Exception:
            warning=(warning+' 已保留生成的回复，按原顺序展示。').strip()
    return {'verdict':verdict,'candidates':candidates,'warning':warning}
