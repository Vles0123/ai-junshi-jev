"""Read visible WeChat message controls using macOS Accessibility, without screenshots."""
import time
import AppKit
import ApplicationServices as AS
import fill
from perception import Message, WindowInfo, WECHAT_APP_NAMES
from apps.ax_app import AXReader, walk, window_id, fingerprint, _inside, _intersects


def identifier(el):
    return fill._ax_attr(el, 'AXIdentifier') or ''


def choose_window(ax, app_root, identify=identifier):
    windows=ax.windows(app_root)
    focused=ax.focused_window(app_root)
    ordered=([focused] if focused is not None else [])+[w for w in windows if w != focused]
    for win in ordered:
        nodes=list(walk(ax,win))
        editor=next((e for e in nodes if identify(e)=='chat_input_field'),None)
        messages=next((e for e in nodes if identify(e)=='chat_message_list'),None)
        title_node=next((e for e in nodes if identify(e)=='current_chat_name_label'),None)
        if editor is not None and messages is not None:
            title=ax.value(title_node) if title_node is not None else ax.desc(editor)
            return win,editor,messages,title or ax.title(win)
    return None,None,None,''


def extract(ax,win,message_list,limit=12,identify=identifier):
    wr=ax.rect(win);lr=ax.rect(message_list)
    if not wr or not lr: return []
    out=[]
    for node in walk(ax,message_list,prune=lambda e:e is not message_list and identify(e)=='chat_bubble_item_view'):
        if identify(node)!='chat_bubble_item_view':continue
        text=(ax.value(node) or ax.desc(node) or ax.title(node)).strip()
        r=ax.rect(node)
        if not text or not r or r[3]<=1 or not _intersects(r,lr) or not _intersects(r,wr):continue
        if text in ('图片','动画表情','视频','语音','文件') or text.startswith('动画表情 ['):continue
        # A full-width row does not reveal who sent it. Do not guess its sender.
        left=r[0]-lr[0];right=lr[0]+lr[2]-r[0]-r[2]
        side='unknown'
        if r[2]<lr[2]*.90 and abs(left-right)>18:
            side='them' if left<right else 'me'
        x,y,w,h=r;wx,wy,ww,wh=wr
        out.append(Message(text,side,(y-wy)/wh,1.0,h/wh,'发送方未确认' if side=='unknown' else None,[text],(x-wx)/ww,w/ww,(y-wy)/wh))
    out.sort(key=lambda m:m.y)
    return out[-limit:]


class WeChatAXApp:
    key='wechat'
    display_name='微信（文字读取）'
    bundle_ids=(fill.WECHAT_BUNDLE_ID,)
    app_names=WECHAT_APP_NAMES
    needs_screen_capture=False

    def _current(self):
        apps=AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(fill.WECHAT_BUNDLE_ID)
        if not apps:return None
        app=apps[0];ax=AXReader()
        root=AS.AXUIElementCreateApplication(app.processIdentifier())
        win,editor,messages,title=choose_window(ax,root)
        r=ax.rect(win) if win is not None else None
        if not r:return None
        wid=window_id(app.processIdentifier(),r)
        return ax,win,editor,messages,WindowInfo(wid,app.processIdentifier(),title,*r)

    def find_window(self,previous_wid=None):
        state=self._current()
        return state[-1] if state else None

    def read_conversation(self,max_messages=60,previous_wid=None,prev_fingerprint=None,prev_layout=None):
        t=time.perf_counter();state=self._current()
        if not state:return {'ok':False,'error':'未找到可读取的微信聊天窗口，请打开具体会话。','messages':[]}
        ax,win,editor,message_list,info=state
        msgs=extract(ax,win,message_list,max_messages)
        fp=fingerprint(info.title,msgs);layout=(info.wid,info.w,info.h)
        window={'wid':info.wid,'title':info.title,'x':info.x,'y':info.y,'w':info.w,'h':info.h}
        unchanged=layout==prev_layout and fp==prev_fingerprint
        elapsed=(time.perf_counter()-t)*1000
        return {'ok':True,'analyze_visible':True,'unchanged':unchanged,'messages':[] if unchanged else msgs,
                'chat_title':info.title,'window':window,'input_rect':ax.rect(editor),
                'input_unresolved':False,'layout':layout,'fingerprint':fp,'n_blocks':len(msgs),
                'timing_ms':{'capture':elapsed,'ocr':0.,'total':elapsed,'capture_path':'wechat-ax'}}

    def locate_input(self,win):return fill.locate_input(win)
    def fill_text(self,text,target=None):return fill.fill_text(text,target=target)
    def warm(self):return None
