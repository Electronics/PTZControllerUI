import logging

from PyQt5 import QtCore
from PyQt5.QtCore import QObject

log = logging.getLogger("ButtonControl")
log.setLevel(logging.INFO)


class ButtonControl(QObject):
    functionPressDict = {} # a way of dynamically changing what the buttons do in a nice-ish way
    functionRelaseDict = {}
    shortcutDict = {} # when shortcuts (numpad) is active for presets
    def __init__(self, parent):
        super().__init__()
        self.UI = parent
        self.shortcutsActive = False

    typingPos = -1  # track where in an input string we are, -1 = no input
    typingString = ""
    typingStringOriginal = ""
    typingCallback = None

    def typingOff(self):
        self.typingPos = -1
        self.typingString = ""
        self.UI.typingFrame.hide()

    def typingOn(self):
        self.UI.typingFrame.show()
        self.UI.typingInput.setFocus()
        if self.typingPos<0:
            self.typingPos = 0

    def setShortcutActive(self, state):
        self.shortcutsActive = state
    def isShortcutActive(self):
        return self.shortcutsActive

    def input(self, s, title="", callback=None):
        # callback should be a function with the arguments (string), if the returned string is None, cancel was pressed
        self.typingString = s
        self.typingStringOriginal = s # for undo operations
        self.typingPos=0
        self.typingCallback = callback
        self.UI.typingTitle.setText(title)
        self.typingOn()
        self.typingUpdate()

    def typingUpdate(self):
        self.UI.typingInput.setText(self.typingString)
        self.UI.typingInput.setFocus()
        self.UI.typingInput.setCursorPosition(self.typingPos)

    skipableCharacters = [",","."]
    def checkTypeSkip(self,direction=0): # dir = 0 (forward) or -1 (backward) normally
        if (self.typingPos+direction) < 0 or \
                (self.typingPos+direction)>=len(self.typingStringOriginal) or \
                self.typingStringOriginal == "":
            return
        if self.typingStringOriginal[self.typingPos+direction] in self.skipableCharacters:
            self.typingPos+=direction or 1

    def typeChar(self, c):
        if self.typingPos<0 or (self.typingString=="" and self.typingStringOriginal!=""): # honestly don't remember why the typingstring=="" is here
            return
        self.typingString = self.typingString[:self.typingPos]+c+ self.typingString[self.typingPos+1:]
        self.typingPos += 1
        self.checkTypeSkip()
        self.typingUpdate()

    def escape(self):
        #self.typingCallback(None) # don't do anything?
        self.typingOff()

    def backspace(self):
        if self.typingPos==0:
            self.typingCallback(None)
            self.typingOff()
        if self.typingPos<=0:
            return
        self.checkTypeSkip(-1)
        self.typingPos -= 1
        if self.typingStringOriginal=="":
            # the original string was blank, so just backspace
            self.typingString = self.typingString[:self.typingPos]
        else:
            self.typingString = self.typingString[:self.typingPos] + self.typingStringOriginal[self.typingPos] + self.typingString[self.typingPos + 1:]
        self.typingUpdate()

    def buttonEvent(self, button, release=False):
        if release:
            functionDict = self.functionRelaseDict
        else:
            functionDict = self.functionPressDict
        if isinstance(button, int):
            # numpad
            if button==-1:
                # backspace
                self.backspace()
            elif button==10:
                # enter
                if self.typingPos >= 0:
                    retStr = self.UI.typingInput.text()
                    self.typingOff()
                    # validity should be checked in the callback
                    # as well as any feedback to the user
                    self.typingCallback(retStr)
                else:
                    if "Enter" in functionDict:
                        functionDict["Enter"]()
            else:
                if self.shortcutsActive:
                    self.shortcutDict[str(button)]()
                else:
                    self.typeChar(str(button))
        else:
            s = str(button)
            if s in functionDict:
                functionDict[s]()

    def guiButtonEvent(self, event, button, release=False):
        self.buttonEvent(button,release=release)

    def connectUIButtons(self):
        self.UI.labelTopLeft.mousePressEvent = lambda event: self.guiButtonEvent(event,"TopLeft")
        self.UI.labelMidLeft.mousePressEvent = lambda event: self.guiButtonEvent(event,"MidLeft")
        self.UI.labelBottomLeft.mousePressEvent = lambda event: self.guiButtonEvent(event,"BottomLeft")
        self.UI.labelCenterLeft.mousePressEvent = lambda event: self.guiButtonEvent(event,"CenterLeft")
        self.UI.labelCenterMid.mousePressEvent = lambda event: self.guiButtonEvent(event,"CenterMid")
        self.UI.labelCenterRight.mousePressEvent = lambda event: self.guiButtonEvent(event,"CenterRight")
        self.UI.labelBottomRight.mousePressEvent = lambda event: self.guiButtonEvent(event,"BottomRight")
        self.UI.labelMidRight.mousePressEvent = lambda event: self.guiButtonEvent(event,"MidRight")
        self.UI.labelTopRight.mousePressEvent = lambda event: self.guiButtonEvent(event,"TopRight")
        self.UI.labelTopLeft.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "TopLeft", release=True)
        self.UI.labelMidLeft.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "MidLeft", release=True)
        self.UI.labelBottomLeft.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "BottomLeft", release=True)
        self.UI.labelCenterLeft.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "CenterLeft", release=True)
        self.UI.labelCenterMid.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "CenterMid", release=True)
        self.UI.labelCenterRight.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "CenterRight", release=True)
        self.UI.labelBottomRight.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "BottomRight", release=True)
        self.UI.labelMidRight.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "MidRight", release=True)
        self.UI.labelTopRight.mouseReleaseEvent = lambda event: self.guiButtonEvent(event, "TopRight", release=True)

        # "debug" buttons
        self.UI.buttonPrev.clicked.connect(lambda: self.buttonEvent("Prev"))
        self.UI.buttonNext.clicked.connect(lambda: self.buttonEvent("Next"))
        self.UI.button0.clicked.connect(lambda: self.buttonEvent(0))
        self.UI.button1.clicked.connect(lambda: self.buttonEvent(1))
        self.UI.button2.clicked.connect(lambda: self.buttonEvent(2))
        self.UI.button3.clicked.connect(lambda: self.buttonEvent(3))
        self.UI.button4.clicked.connect(lambda: self.buttonEvent(4))
        self.UI.button5.clicked.connect(lambda: self.buttonEvent(5))
        self.UI.button6.clicked.connect(lambda: self.buttonEvent(6))
        self.UI.button7.clicked.connect(lambda: self.buttonEvent(7))
        self.UI.button8.clicked.connect(lambda: self.buttonEvent(8))
        self.UI.button9.clicked.connect(lambda: self.buttonEvent(9))
        self.UI.buttonClear.clicked.connect(lambda: self.buttonEvent(-1))
        self.UI.buttonEnter.clicked.connect(lambda: self.buttonEvent(10))

    def connectFunctions(self, pDict, rDict=None): # pressed, released dicts
        self.functionPressDict = pDict
        self.functionRelaseDict = {}
        if rDict:
            self.functionRelaseDict = rDict

    def connectShortcutFunctions(self, fDict):
        self.shortcutDict = fDict

    def decodeButton(self, num, press=True): # press=False is a release event
        buttonMap = [
            self.Button1, # 0,0
            self.Button2,
            self.Button3,
            None,
            self.Button9,
            self.Button4,
            self.Button5,
            self.Button6, # 0,7
            self.Button0, # 1,0
            self.ButtonEnter,
            self.Button7,
            self.Button8,
            self.ButtonBottomLeft,
            self.ButtonMidLeft,
            self.ButtonTopLeft,
            self.ButtonCenterLeft, # 1,7
            self.ButtonCenterMid, # 2,0
            self.ButtonCenterRight,
            self.ButtonPrev,
            self.ButtonNext,
            self.ButtonTopRight,
            self.ButtonMidRight,
            self.ButtonBottomRight,
            self.ButtonClear
        ]
        buttonMap[num](release=not press)
    def decodeButtonRelease(self, num):
        self.decodeButton(num,press=False)