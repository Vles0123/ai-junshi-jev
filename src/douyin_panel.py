"""Manual Douyin DM panel: capture/import -> review -> explicit analysis -> copy."""
from __future__ import annotations
import subprocess
import tempfile
import threading
import time
import urllib.error
from pathlib import Path
import AppKit as A
import Quartz
import objc
from Foundation import NSObject, NSMakeRect, NSData
import douyin_flow as flow
from generate import Generator, load_credentials
from judge import make_judge
from judge_jev import jev_configured
import userconfig


class DouyinController(NSObject):
    @objc.python_method
    def build(self,hud):
        self.hud=hud;self.revision=flow.Revision();self.busy=False;self.replies=[];self.picker=None
        self.window=A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0,0,760,740),A.NSWindowStyleMaskTitled|A.NSWindowStyleMaskClosable|A.NSWindowStyleMaskMiniaturizable,
            A.NSBackingStoreBuffered,False)
        self.window.setTitle_('ai 军师 jev 改进版 · 抖音私信')
        self.window.setReleasedWhenClosed_(False);self.window.setDelegate_(self)
        self.window.setLevel_(A.NSFloatingWindowLevel)
        self.window.setAppearance_(A.NSAppearance.appearanceNamed_(A.NSAppearanceNameAqua))
        self.view=self.window.contentView()
        self.view.setWantsLayer_(True)
        self.view.layer().setBackgroundColor_(A.NSColor.colorWithWhite_alpha_(.96,1).CGColor())
        self.label('抖音私信',24,693,500,32,24)
        self.label('框选消息或导入截图 → 校对 → 分析 → 复制回复',24,668,710,22,12)
        self.capture=self.button('框选私信区','capture:',24,627,138)
        self.import_button=self.button('导入截图','importImage:',174,627,116)
        self.paste=self.button('粘贴文字','pasteText:',302,627,116)
        self.clear=self.button('清空 / 换会话','clear:',430,627,152)
        self.settings=self.button('模型设置','settings:',594,627,138)
        self.label('会话备注',24,591,70,20,12)
        self.contact=A.NSTextField.alloc().initWithFrame_(NSMakeRect(96,589,178,25))
        self.contact.setPlaceholderString_('选填，例如：小王');self.contact.setDelegate_(self);self.view.addSubview_(self.contact)
        self.label('关系背景',294,591,70,20,12)
        self.background=A.NSTextField.alloc().initWithFrame_(NSMakeRect(366,589,366,25))
        self.background.setPlaceholderString_('选填，只写已知事实');self.background.setDelegate_(self);self.view.addSubview_(self.background)
        self.label('每条以“我：”或“对方：”开头；删掉时间、昵称和页面按钮，末条为待回复消息。',24,558,712,22,11)
        self.preview=A.NSImageView.alloc().initWithFrame_(NSMakeRect(24,354,172,194))
        self.preview.setImageScaling_(A.NSImageScaleProportionallyUpOrDown)
        self.view.addSubview_(self.preview)
        self.editor=self.textbox(210,354,522,194,True)
        self.editor.setDelegate_(self)
        self.review=A.NSButton.alloc().initWithFrame_(NSMakeRect(24,312,464,28))
        self.review.setButtonType_(A.NSSwitchButton);self.review.setTitle_('文字与发言人已核对（左右归属只是初步识别）')
        self.view.addSubview_(self.review)
        self.run_button=self.button('分析对话','analyze:',576,308,156)
        self.status=self.label('只在点分析后发送校对文字；截图在本机识别。',24,278,710,26,12)
        summary_box=A.NSView.alloc().initWithFrame_(NSMakeRect(16,224,728,54))
        summary_box.setWantsLayer_(True);summary_box.layer().setCornerRadius_(9)
        summary_box.layer().setBackgroundColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(.92,.95,.99,1).CGColor())
        self.view.addSubview_(summary_box)
        self.summary=self.label('分析结论｜等待分析',28,229,700,44,13)
        self.summary.setTextColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(.13,.24,.40,1))
        self.summary.setFont_(A.NSFont.boldSystemFontOfSize_(13))
        reply_heading=self.label('参考回复 · 分析后在这里显示，可单独复制',24,200,700,22,12)
        reply_heading.setTextColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(.08,.36,.26,1))
        reply_heading.setFont_(A.NSFont.boldSystemFontOfSize_(12))
        self.summary.setSelectable_(True)
        self.output=[];self.copy_buttons=[]
        for i,y in enumerate((143,81,19)):
            box=self.textbox(24,y,590,55,False)
            box.setBackgroundColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(.89,.96,.92,1))
            box.setTextColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(.10,.25,.18,1))
            box.setString_(flow.TONES[i]+' · 等待生成参考回复')
            self.output.append(box)
            button=self.button('复制','copyReply:',632,y+9,100);button.setTag_(i);button.setEnabled_(False)
            button.setBezelColor_(A.NSColor.colorWithSRGBRed_green_blue_alpha_(.16,.48,.34,1))
            self.copy_buttons.append(button)
        return self

    @objc.python_method
    def label(self,text,x,y,w,h,size):
        label=A.NSTextField.wrappingLabelWithString_(text)
        label.setFrame_(NSMakeRect(x,y,w,h));label.setFont_(A.NSFont.systemFontOfSize_(size));self.view.addSubview_(label)
        return label

    @objc.python_method
    def button(self,title,selector,x,y,w):
        b=A.NSButton.alloc().initWithFrame_(NSMakeRect(x,y,w,32));b.setTitle_(title)
        b.setBezelStyle_(A.NSBezelStyleRounded);b.setTarget_(self);b.setAction_(selector);self.view.addSubview_(b)
        return b

    @objc.python_method
    def textbox(self,x,y,w,h,editable):
        scroll=A.NSScrollView.alloc().initWithFrame_(NSMakeRect(x,y,w,h))
        scroll.setBorderType_(A.NSBezelBorder);scroll.setHasVerticalScroller_(True)
        text=A.NSTextView.alloc().initWithFrame_(NSMakeRect(0,0,w-18,h))
        text.setFont_(A.NSFont.systemFontOfSize_(13));text.setRichText_(False)
        text.setEditable_(editable);text.setSelectable_(True)
        text.setHorizontallyResizable_(False);text.setVerticallyResizable_(True)
        text.setAutoresizingMask_(A.NSViewWidthSizable)
        text.textContainer().setWidthTracksTextView_(True)
        text.textContainer().setContainerSize_((w-18,10_000_000))
        scroll.setDocumentView_(text);self.view.addSubview_(scroll)
        return text

    @objc.python_method
    def show(self):
        if not self.hud._paused:self.hud.togglePause_(None)
        self.hud.panel.orderOut_(None)
        self.window.center();self.window.makeKeyAndOrderFront_(None)
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    @objc.python_method
    def invalidate(self):
        token=self.revision.next();self.review.setState_(A.NSControlStateValueOff)
        self.replies=[];self.summary.setStringValue_('分析结论｜等待分析')
        for i,(box,button) in enumerate(zip(self.output,self.copy_buttons)):
            box.setString_(flow.TONES[i]+' · 等待生成参考回复');button.setEnabled_(False)
        return token

    @objc.python_method
    def set_busy(self,value):
        self.busy=value
        for control in (self.capture,self.import_button,self.paste,self.run_button,self.contact,self.background,self.review,self.settings):
            control.setEnabled_(not value)
        self.editor.setEditable_(not value)

    def textDidChange_(self,note): self.invalidate()
    def controlTextDidChange_(self,note): self.invalidate()

    def clear_(self,sender):
        self.invalidate();self.set_busy(False);self.editor.setString_('');self.preview.setImage_(None)
        self.contact.setStringValue_('');self.background.setStringValue_('')
        self.status.setStringValue_('已清空。导入另一段私信后重新校对；旧请求的结果不会显示。')

    def windowWillClose_(self,note): self.clear_(None)
    def settings_(self,sender): self.hud.openSettings_(None)

    def pasteText_(self,sender):
        text=A.NSPasteboard.generalPasteboard().stringForType_(A.NSPasteboardTypeString)
        if not text:self.status.setStringValue_('剪贴板没有文字。');return
        self.invalidate();self.editor.setString_(str(text));self.preview.setImage_(None)
        self.status.setStringValue_('请核对“我 / 对方”的归属，再勾选已核对。')

    def importImage_(self,sender):
        panel=A.NSOpenPanel.openPanel();panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False);panel.setAllowedFileTypes_(['png','jpg','jpeg','heic','webp','tiff'])
        if panel.runModal()!=A.NSModalResponseOK:return
        token=self.invalidate();self.set_busy(True);self.status.setStringValue_('正在本机识别截图…')
        path=str(panel.URL().path())
        threading.Thread(target=self.ocr_worker,args=(token,path,None),daemon=True).start()

    def capture_(self,sender):
        from perception import screen_capture_ok,request_screen_capture
        if not screen_capture_ok():
            request_screen_capture();self.status.setStringValue_('请允许 ai 军师 jev 改进版 录屏后重启应用，再框选。');return
        from region_picker import RegionPicker
        token=self.invalidate();self.set_busy(True);self.window.orderOut_(None);self.hud.panel.orderOut_(None)
        def selected(rect):
            self.picker=None
            if rect is None:
                self.set_busy(False);self.window.makeKeyAndOrderFront_(None);self.status.setStringValue_('已取消框选。');return
            threading.Thread(target=self.ocr_worker,args=(token,None,rect),daemon=True).start()
        self.picker=RegionPicker(selected);self.picker.show()

    @objc.python_method
    def ocr_worker(self,token,path,rect):
        try:
            import Quartz
            from perception import _load_png_image,ocr_image
            with tempfile.TemporaryDirectory(prefix='vles-douyin-') as temp:
                if rect is not None:
                    # Picker windows must disappear before taking the selected pixels.
                    time.sleep(.25)
                    path=str(Path(temp)/'capture.png')
                    result=subprocess.run(['/usr/sbin/screencapture','-x','-t','png','-R'+','.join(map(str,rect)),path],
                                          timeout=3,capture_output=True)
                    if result.returncode!=0 or not Path(path).exists():
                        raise ValueError('截图失败，请检查录屏权限或改用导入截图。')
                source=Path(path)
                if source.stat().st_size>40*1024*1024:raise ValueError('图片过大，请拆成较短的截图。')
                image=_load_png_image(source)
                if image is None:raise ValueError('图片无法读取，请使用 PNG 或 JPEG。')
                if Quartz.CGImageGetWidth(image)*Quartz.CGImageGetHeight(image)>32_000_000:
                    raise ValueError('长截图过大，请分段导入。')
                blocks=ocr_image(image,chat_only=False)
                draft=flow.ocr_draft(blocks)
                if not draft.strip():raise ValueError('没有识别到文字，请换一张清晰的截图。')
                payload={'kind':'ocr','token':token,'text':draft,'image':source.read_bytes()}
        except Exception as error:
            payload={'kind':'error','token':token,'message':self.error_message(error)}
        self.performSelectorOnMainThread_withObject_waitUntilDone_('applyResult:',payload,False)

    def analyze_(self,sender):
        if self.busy:return
        if self.review.state()!=A.NSControlStateValueOn:
            self.status.setStringValue_('先校对文字、发言人和最后一条消息，再勾选“已核对”。');return
        try:
            conversation=flow.prepare(str(self.editor.string()),str(self.contact.stringValue()),str(self.background.stringValue()))
            if userconfig.get('JUDGE_BACKEND') == 'cloud' and not jev_configured():raise ValueError('请在模型设置填写 Jev Key，保存后重启。')
            if not load_credentials()[1]:raise ValueError('请在模型设置填写回复模型 Key，保存后重启。')
        except ValueError as error:
            self.status.setStringValue_(str(error));return
        token=self.revision.next();self.set_busy(True);self.replies=[]
        for i,(box,button) in enumerate(zip(self.output,self.copy_buttons)):
            box.setString_(flow.TONES[i]+' · 正在生成…');button.setEnabled_(False)
        self.summary.setStringValue_('正在分析已校对的对话…')
        self.status.setStringValue_('已发送校对文字到所配置模型，正在判断并生成候选…')
        threading.Thread(target=self.analysis_worker,args=(token,conversation),daemon=True).start()

    @objc.python_method
    def analysis_worker(self,token,conversation):
        try:
            result=flow.analyze(conversation,make_judge(),Generator())
            payload={'kind':'analysis','token':token,'result':result}
        except Exception as error:
            payload={'kind':'error','token':token,'message':self.error_message(error)}
        self.performSelectorOnMainThread_withObject_waitUntilDone_('applyResult:',payload,False)

    @objc.python_method
    def error_message(self,error):
        if isinstance(error,urllib.error.HTTPError):
            return {401:'密钥无效，请检查当前分析和回复模型配置。',402:'接口余额不足。',429:'请求过于频繁或接口限流，请稍后再试。'}.get(error.code,f'模型接口 HTTP {error.code}，请检查配置。')
        if isinstance(error,(TimeoutError,subprocess.TimeoutExpired)):return '操作超时，请重试或改用导入截图。'
        if isinstance(error,ValueError):return str(error)
        return '操作失败（'+type(error).__name__+'），请检查网络、权限或模型设置。'

    def applyResult_(self,payload):
        if not self.revision.current(payload['token']):return
        self.set_busy(False);self.window.makeKeyAndOrderFront_(None)
        if payload['kind']=='error':
            self.status.setStringValue_(payload['message'])
            for box in self.output:box.setString_('本次未完成，请查看上方错误提示后重试。')
            return
        if payload['kind']=='ocr':
            self.editor.setString_(payload['text'])
            data=payload['image'];image=A.NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(data,len(data)))
            self.preview.setImage_(image);self.review.setState_(A.NSControlStateValueOff)
            self.status.setStringValue_('识别完成，尚未上传。请删掉时间/昵称等，并确认左右归属。');return
        result=payload['result'];verdict=result['verdict']
        self.summary.setStringValue_(f"分析结论｜{verdict['intent']} · 倾向 {verdict['confidence']:.0%} · 紧张度 {verdict['risk']}/9\n建议行动："+' · '.join(verdict['actions']))
        self.replies=result['candidates'][:3]
        for row,(box,button) in enumerate(zip(self.output,self.copy_buttons)):
            if row>=len(self.replies):
                box.setString_(flow.TONES[row]+' · 本次未生成，请重试');button.setEnabled_(False);continue
            item=self.replies[row];score='未评分' if item['prob'] is None else f"倾向 {item['prob']:.0%}"
            box.setString_(f"{item['tone']} · {score}\n{item['text']}");button.setEnabled_(True)
        self.status.setStringValue_((f'已生成 {len(self.replies)} 条参考回复 · '+result['warning']) if self.replies else (result['warning'] or '未获得有效回复，请重试。'))

    def copyReply_(self,sender):
        i=sender.tag()
        if not 0<=i<len(self.replies):return
        board=A.NSPasteboard.generalPasteboard();board.clearContents()
        board.setString_forType_(self.replies[i]['text'],A.NSPasteboardTypeString)
        self.status.setStringValue_('已复制候选，请回到对应抖音会话自行粘贴、检查并发送。')
