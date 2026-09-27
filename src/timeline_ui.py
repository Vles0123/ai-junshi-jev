"""Scrollable native per-message cards; copying never writes into a chat."""
import math
import json
from pathlib import Path
import AppKit as A

class TimelineDocument(A.NSView):
    def isFlipped(self):return True

class TimelineView:
    def __init__(self,controller,width):
        self.preferences=Path.home()/'.config/vles-chat/window.json'
        try:
            saved=json.loads(self.preferences.read_text())
            width=max(320,min(1200,float(saved['width'])))
            self.expanded_height=max(280,min(1200,float(saved['height'])))
        except (OSError,ValueError,KeyError,TypeError):
            width=480;self.expanded_height=740
        self.resizing=False;self.follow_window=None
        self.expanded=set();self.detail_buttons=[];self.last_render=None;self.entry_keys=[]
        self.controller=controller;self.width=width;self.scene=None;self.card_views=[];self.replies=[];self.buttons=[]
        self.root=A.NSView.alloc().initWithFrame_(A.NSMakeRect(0,0,width,680))
        self.root.setWantsLayer_(True);self.root.layer().setBackgroundColor_(A.NSColor.colorWithWhite_alpha_(.96,1).CGColor())
        self.title=self.label('逐条消息解读',14,True)
        self.toggle=controller._make_button(0,0,70,28,'开始','togglePause:',0)
        self.toggle.setHidden_(False);self.root.addSubview_(self.toggle)
        self.status=self.label('读取当前聊天…',11,False)
        self.root.addSubview_(self.title);self.root.addSubview_(self.status)
        self.settings=controller._make_button(0,0,54,28,'设置','openSettings:',0)
        self.refresh=controller._make_button(0,0,64,28,'重试','retryTimeline:',0)
        self.settings.setHidden_(False);self.refresh.setHidden_(False)
        self.root.addSubview_(self.settings);self.root.addSubview_(self.refresh)
        self.scroll=A.NSScrollView.alloc().initWithFrame_(A.NSMakeRect(0,0,width,600))
        self.scroll.setDrawsBackground_(False);self.scroll.setHasVerticalScroller_(True)
        self.scroll.setAutohidesScrollers_(True)
        self.doc=TimelineDocument.alloc().initWithFrame_(A.NSMakeRect(0,0,width,600))
        self.scroll.setDocumentView_(self.doc);self.root.addSubview_(self.scroll)
        controller.panel.setStyleMask_(controller.panel.styleMask() | A.NSWindowStyleMaskResizable)
        controller.panel.setContentMinSize_(A.NSMakeSize(320,280))
        self.root.setAutoresizingMask_(A.NSViewWidthSizable | A.NSViewHeightSizable)
        self.size(False)
    def label(self,text,size,bold):
        v=A.NSTextField.alloc().initWithFrame_(A.NSMakeRect(0,0,self.width-56,20))
        v.setEditable_(False);v.setSelectable_(True);v.setBordered_(False);v.setDrawsBackground_(False)
        v.setFont_(A.NSFont.boldSystemFontOfSize_(size) if bold else A.NSFont.systemFontOfSize_(size))
        v.setTextColor_(A.NSColor.colorWithWhite_alpha_(.18,1));v.setStringValue_(text)
        v.setUsesSingleLineMode_(False);v.cell().setWraps_(True);v.cell().setScrollable_(False)
        return v
    def size(self,collapsed):
        c=self.controller;f=c.panel.frame();screen=c.panel.screen() or A.NSScreen.mainScreen()
        available=screen.visibleFrame().size.height-20 if screen else 760
        content=70 if collapsed else min(self.expanded_height,available-c._title_h)
        self.width=min(self.width,screen.visibleFrame().size.width-20) if screen else self.width
        c.panel.setContentMinSize_(A.NSMakeSize(320,70 if collapsed else 280))
        height=content+c._title_h
        self.resizing=True
        c.panel.setFrame_display_(A.NSMakeRect(f.origin.x,f.origin.y+f.size.height-height,self.width,height),True)
        self.layout(self.width,content)
        self.resizing=False
        self.scroll.setHidden_(collapsed)
        if self.last_render:self.render(*self.last_render)

    def layout(self,width,content):
        self.width=width
        self.root.setFrameSize_(A.NSMakeSize(width,content))
        self.title.setFrame_(A.NSMakeRect(12,content-32,max(70,width-230),22))
        self.title.setMaximumNumberOfLines_(1)
        self.title.cell().setLineBreakMode_(A.NSLineBreakByTruncatingTail)
        self.status.setFrame_(A.NSMakeRect(12,content-69,width-24,34))
        self.toggle.setFrame_(A.NSMakeRect(width-208,content-34,70,28))
        self.refresh.setFrame_(A.NSMakeRect(width-134,content-34,64,28))
        self.settings.setFrame_(A.NSMakeRect(width-66,content-34,54,28))
        self.scroll.setFrame_(A.NSMakeRect(0,0,width,max(0,content-76)))

    def resized(self):
        if self.resizing:return
        bounds=self.controller.panel.contentView().bounds()
        self.resizing=True
        self.layout(bounds.size.width,bounds.size.height)
        if not self.controller._collapsed:self.expanded_height=bounds.size.height
        if self.last_render:self.render(*self.last_render)
        self.resizing=False

    def save_size(self):
        if self.controller._collapsed:return
        self.preferences.parent.mkdir(parents=True,exist_ok=True)
        temp=self.preferences.with_suffix('.tmp')
        temp.write_text(json.dumps({'width':self.width,'height':self.expanded_height}))
        temp.replace(self.preferences)

    def follow(self,win):
        # Let edge dragging finish; then follow only actual changes to WeChat's window.
        if self.controller.panel.inLiveResize():return True
        if not win:return False
        current=(win.get('wid'),win['x'],win['y'],win['w'],win['h'])
        previous=self.follow_window;self.follow_window=current
        if previous is None or previous[0]!=current[0]:return False
        if current==previous:return True
        panel=self.controller.panel;f=panel.frame();flip=self.controller._display_height()
        cx=win['x']+win['w']/2;cy=flip-win['y']-win['h']/2
        screens=list(A.NSScreen.screens())
        screen=next((s for s in screens if A.NSPointInRect(A.NSMakePoint(cx,cy),s.frame())),A.NSScreen.mainScreen())
        visible=screen.visibleFrame()
        width=min(f.size.width,visible.size.width);height=min(f.size.height,visible.size.height)
        x=max(visible.origin.x,min(f.origin.x+current[1]-previous[1],visible.origin.x+visible.size.width-width))
        y=max(visible.origin.y,min(f.origin.y-(current[2]-previous[2]),visible.origin.y+visible.size.height-height))
        panel.setFrame_display_(A.NSMakeRect(x,y,width,height),True)
        return True

    def toggle_detail(self,index):
        if not self.last_render or not 0<=index<len(self.entry_keys):return
        key=self.entry_keys[index]
        if key in self.expanded:self.expanded.remove(key)
        else:self.expanded.add(key)
        self.render(*self.last_render)

    def render(self,scene,title,entries,cache,status):
        self.last_render=(scene,title,entries,cache,status)
        self.entry_keys=[e['key'] for e in entries]
        self.expanded.intersection_update(self.entry_keys)
        clip=self.scroll.contentView();old_y=clip.bounds().origin.y
        bottom=old_y+clip.bounds().size.height>=self.doc.frame().size.height-40
        anchor=next(((key,old_y-top) for key,top,height in self.card_views if top<=old_y<top+height),None)
        for button in self.buttons+self.detail_buttons:
            if button in self.controller._appearance_buttons:self.controller._appearance_buttons.remove(button)
        self.buttons=[];self.detail_buttons=[];self.replies=[];self.card_views=[]
        for v in list(self.doc.subviews()):v.removeFromSuperview()
        columns=max(1,min(3,int((self.width-14)//233)))
        y=10;gap=10;margin=12;cw=(self.width-margin*2-gap*(columns-1))/columns;pad=10;inner=cw-pad*2
        muted=A.NSColor.colorWithWhite_alpha_(.46,1)
        ink=A.NSColor.colorWithWhite_alpha_(.17,1)
        green=A.NSColor.colorWithSRGBRed_green_blue_alpha_(.08,.35,.27,1)
        def text(parent,value,x,top,width,size=11,bold=False,color=ink,lines=None):
            label=self.label(value,size,bold)
            para=A.NSMutableParagraphStyle.alloc().init();para.setLineSpacing_(2)
            attr=A.NSAttributedString.alloc().initWithString_attributes_(value,{
                A.NSFontAttributeName:label.font(),A.NSParagraphStyleAttributeName:para,
                A.NSForegroundColorAttributeName:color})
            h=math.ceil(attr.boundingRectWithSize_options_(A.NSMakeSize(width-4,100000),
                A.NSStringDrawingUsesLineFragmentOrigin|A.NSStringDrawingUsesFontLeading).size.height)+5
            if lines:
                h=min(h,math.ceil((size*1.4+2)*lines)+4)
                label.setMaximumNumberOfLines_(lines);label.cell().setLineBreakMode_(A.NSLineBreakByTruncatingTail)
            label.setToolTip_(value);label.setAttributedStringValue_(attr)
            label.setFrame_(A.NSMakeRect(x,top,width,h));parent.addSubview_(label)
            return top+h
        def weights(items):return ' · '.join(f"{v['label']} {v['weight']:.0%}" for v in items)
        for row_start in range(0,len(entries),columns):
            row=[]
            for col,e in enumerate(entries[row_start:row_start+columns]):
                index=row_start+col;result=cache.get(e['key']);expanded=e['key'] in self.expanded
                surface=TimelineDocument.alloc().initWithFrame_(A.NSMakeRect(margin+col*(cw+gap),y,cw,100))
                surface.setWantsLayer_(True);surface.layer().setBackgroundColor_(A.NSColor.whiteColor().CGColor())
                surface.layer().setCornerRadius_(10);self.doc.addSubview_(surface)
                def block(top,color,border=False):
                    view=TimelineDocument.alloc().initWithFrame_(A.NSMakeRect(7,top,cw-14,100))
                    view.setWantsLayer_(True);view.layer().setCornerRadius_(7)
                    view.layer().setBackgroundColor_(color.CGColor())
                    if border:
                        view.layer().setBorderColor_(A.NSColor.colorWithWhite_alpha_(.88,1).CGColor())
                        view.layer().setBorderWidth_(.6)
                    surface.addSubview_(view)
                    return view
                bw=cw-14;bi=bw-18
                blue=A.NSColor.colorWithSRGBRed_green_blue_alpha_(.14,.23,.38,1)
                who={'them':'对方','me':'我'}.get(e['side'],'来源待确认')
                original=block(7,A.NSColor.colorWithWhite_alpha_(.96,1),True)
                ot=text(original,f'{index+1:02d} · 原消息 · {who}',9,8,bi,9,False,muted)
                ot=text(original,e['text'],9,ot+4,bi,12,True,lines=None if expanded else 2)+9
                original.setFrameSize_(A.NSMakeSize(bw,ot));top=7+ot+8
                if result:
                    intent=max(result['intent'],key=lambda item:item['weight'])
                    action=max(result['actions'],key=lambda item:item['weight'])
                    summary=block(top,A.NSColor.colorWithSRGBRed_green_blue_alpha_(.93,.95,.98,1))
                    st=text(summary,'可能意图',9,8,bi-60,9,False,muted)
                    st=text(summary,intent['label'],9,st+3,bi-60,14,True,blue)
                    st=text(summary,f"模型倾向 {intent['weight']:.0%}",9,st+2,bi-60,10,False,muted)+9
                    risk=result['risk'];risk_color=A.NSColor.colorWithSRGBRed_green_blue_alpha_(.78,.24,.22,1) if risk>=7 else A.NSColor.colorWithSRGBRed_green_blue_alpha_(.62,.40,.10,1) if risk>=4 else green
                    text(summary,'紧张度',bw-62,8,55,9,False,muted)
                    rt=text(summary,f'{risk:.0f}/10',bw-62,26,55,14,True,risk_color)
                    rt=text(summary,'高' if risk>=7 else '中' if risk>=4 else '低',bw-62,rt+2,55,10,False,risk_color)+9
                    sh=max(st,rt);summary.setFrameSize_(A.NSMakeSize(bw,sh));top+=sh+7
                    action_view=block(top,A.NSColor.colorWithWhite_alpha_(.97,1))
                    at=text(action_view,'具体行动',9,8,bi,10,True,blue)
                    at=text(action_view,action['label'],9,at+3,bi,11,False,ink,lines=None if expanded else 2)+9
                    action_view.setFrameSize_(A.NSMakeSize(bw,at));top+=at+8
                    if expanded:
                        detail_view=block(top,A.NSColor.whiteColor(),True)
                        dt=text(detail_view,'这句话怎么理解',9,9,bi,11,True,blue)
                        dt=text(detail_view,result['question'],9,dt+5,bi,11,True)
                        def probability_rows(items,top):
                            for item in items:
                                end=text(detail_view,item['label'],9,top,bi-38,10,False,ink)
                                text(detail_view,f"{item['weight']:.0%}",bw-44,top,36,10,True,blue)
                                top=end+2
                            return top
                        dt=probability_rows(result['reading'],dt+5)
                        dt=text(detail_view,'可能意图',9,dt+8,bi,11,True,blue)
                        dt=probability_rows(result['intent'],dt+5)
                        dt=text(detail_view,'建议行动',9,dt+8,bi,11,True,blue)
                        dt=probability_rows(result['actions'],dt+5)
                        dt=text(detail_view,f"模型估计 · 参考上文 {e['context_count']} 条",9,dt+7,bi,9,False,muted)+9
                        detail_view.setFrameSize_(A.NSMakeSize(bw,dt));top+=dt+8
                    reply=TimelineDocument.alloc().initWithFrame_(A.NSMakeRect(7,top,cw-14,100))
                    reply.setWantsLayer_(True);reply.layer().setCornerRadius_(7)
                    reply.layer().setBackgroundColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(.89,.96,.92,1).CGColor())
                    surface.addSubview_(reply);rw=cw-14
                    heading='参考回复' if e['side']=='them' else '参考回复 · 若为对方消息' if e['side']=='unknown' else '可补充的话'
                    rt=text(reply,heading,8,7,rw-16,10,True,green)
                    rt=text(reply,result['reply'],8,rt+3,rw-16,12,False,ink,lines=None if expanded else 4)+6
                    idx=len(self.replies);self.replies.append(result['reply'])
                    button=self.controller._make_button(rw-66,rt,58,23,'复制','copyTimeline:',idx)
                    button.setHidden_(False);button.setToolTip_('复制完整参考回复')
                    button.layer().setBackgroundColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(.12,.43,.31,1).CGColor())
                    button.setContentTintColor_(A.NSColor.whiteColor());reply.addSubview_(button);self.buttons.append(button)
                    rt+=30;reply.setFrameSize_(A.NSMakeSize(rw,rt));top+=rt+5
                else:top=text(surface,'等待分析…',pad,top,inner,11,False,muted)+7
                detail=self.controller._make_button(cw-78,top,68,23,'收起' if expanded else '展开详情','toggleTimelineDetail:',index)
                detail.setHidden_(False);surface.addSubview_(detail);self.detail_buttons.append(detail)
                height=top+30;surface.setFrameSize_(A.NSMakeSize(cw,height));row.append((e['key'],surface,height))
            row_height=max(item[2] for item in row)
            for key,surface,height in row:
                surface.setFrameSize_(A.NSMakeSize(cw,row_height))
                self.card_views.append((key,y,row_height+gap))
            y+=row_height+gap
        self.doc.setFrameSize_(A.NSMakeSize(self.width,max(y,clip.bounds().size.height)))
        self.title.setStringValue_(title or '逐条消息解读')
        self.status.setStringValue_(status+'\n判断仅供参考 · 详情可展开')
        target=old_y
        if scene!=self.scene or bottom:target=max(0,y-clip.bounds().size.height)
        elif anchor:target=next((top+anchor[1] for key,top,h in self.card_views if key==anchor[0]),old_y)
        target=max(0,min(target,max(0,y-clip.bounds().size.height)))
        clip.scrollToPoint_(A.NSMakePoint(0,target));self.scroll.reflectScrolledClipView_(clip)
        self.scene=scene;self.toggle.setTitle_("开始" if self.controller._paused else "暂停")
