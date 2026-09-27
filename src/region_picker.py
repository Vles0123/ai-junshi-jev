"""Native multi-display rectangle picker; screenshot itself has a 3-second timeout."""
import AppKit as A
import objc
from Foundation import NSMakeRect
from douyin_flow import capture_rect


class SelectionPanel(A.NSPanel):
    def canBecomeKeyWindow(self): return True


class SelectionView(A.NSView):
    def acceptsFirstResponder(self): return True

    def mouseDown_(self,event):
        p=self.convertPoint_fromView_(event.locationInWindow(),None)
        self.start=(p.x,p.y);self.selection=None

    def mouseDragged_(self,event):
        if self.start is None:return
        p=self.convertPoint_fromView_(event.locationInWindow(),None)
        x,y=self.start
        self.selection=(min(x,p.x),min(y,p.y),abs(x-p.x),abs(y-p.y))
        self.setNeedsDisplay_(True)

    def mouseUp_(self,event):
        self.mouseDragged_(event)
        if self.selection and self.selection[2]>=20 and self.selection[3]>=20:
            r=capture_rect(self.origin,self.selection,self.primary_height)
            self.picker.finish(r)

    def keyDown_(self,event):
        if event.keyCode()==53:self.picker.finish(None)
        else:super().keyDown_(event)

    def drawRect_(self,rect):
        A.NSColor.colorWithCalibratedWhite_alpha_(0,.28).setFill()
        A.NSRectFill(self.bounds())
        if self.selection:
            r=NSMakeRect(*self.selection)
            A.NSRectFillUsingOperation(r,A.NSCompositingOperationClear)
            A.NSColor.whiteColor().setStroke()
            path=A.NSBezierPath.bezierPathWithRect_(r);path.setLineWidth_(2);path.stroke()


class RegionPicker:
    def __init__(self,callback):
        self.callback=callback;self.windows=[];self.done=False

    def show(self):
        screens=A.NSScreen.screens()
        if not screens:self.finish(None);return
        primary_height=screens[0].frame().size.height
        for screen in screens:
            f=screen.frame()
            window=SelectionPanel.alloc().initWithContentRect_styleMask_backing_defer_(f,A.NSWindowStyleMaskBorderless,A.NSBackingStoreBuffered,False)
            window.setReleasedWhenClosed_(False);window.setOpaque_(False)
            window.setBackgroundColor_(A.NSColor.clearColor());window.setLevel_(A.NSStatusWindowLevel+3)
            window.setCollectionBehavior_(A.NSWindowCollectionBehaviorCanJoinAllSpaces|A.NSWindowCollectionBehaviorFullScreenAuxiliary)
            view=SelectionView.alloc().initWithFrame_(NSMakeRect(0,0,f.size.width,f.size.height))
            view.start=None;view.selection=None;view.origin=(f.origin.x,f.origin.y)
            view.primary_height=primary_height;view.picker=self
            label=A.NSTextField.labelWithString_('拖动框选抖音私信消息区 · 不含输入框和联系人列表 · Esc 取消')
            label.setTextColor_(A.NSColor.whiteColor());label.setFont_(A.NSFont.boldSystemFontOfSize_(17))
            label.setFrame_(NSMakeRect(32,f.size.height-80,max(100,f.size.width-64),30))
            view.addSubview_(label);window.setContentView_(view);self.windows.append(window)
            window.makeKeyAndOrderFront_(None);window.makeFirstResponder_(view)
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def finish(self,rect):
        if self.done:return
        self.done=True
        for window in self.windows:window.orderOut_(None);window.close()
        self.callback(rect)
