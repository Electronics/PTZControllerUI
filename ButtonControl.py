import logging

from PyQt5.QtCore import QObject

log = logging.getLogger("ButtonControl")
log.setLevel(logging.INFO)


class ButtonControl(QObject):
    functionDict = {} # a way of dynamically changing what the buttons do in a nice-ish way
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

    def ButtonTopLeft(self,event=None):
        log.debug("Button Top Left Pressed")
        if "TopLeft" in self.functionDict:
            self.functionDict["TopLeft"]()
    def ButtonMidLeft(self,event=None):
        log.debug("Button Mid Left Pressed")
        if "MidLeft" in self.functionDict:
            self.functionDict["MidLeft"]()
    def ButtonBottomLeft(self,event=None):
        log.debug("Button Bottom Left Pressed")
        if "BottomLeft" in self.functionDict:
            self.functionDict["BottomLeft"]()
    def ButtonCenterLeft(self,event=None):
        log.debug("Button Center Left Pressed")
        if "CenterLeft" in self.functionDict:
            self.functionDict["CenterLeft"]()
    def ButtonCenterMid(self,event=None):
        log.debug("Button Center Mid Pressed")
        if "CenterMid" in self.functionDict:
            self.functionDict["CenterMid"]()
    def ButtonCenterRight(self,event=None):
        log.debug("Button Center Right Pressed")
        if "CenterRight" in self.functionDict:
            self.functionDict["CenterRight"]()
    def ButtonBottomRight(self,event=None):
        log.debug("Button Bottom Right Pressed")
        if "BottomRight" in self.functionDict:
            self.functionDict["BottomRight"]()
    def ButtonMidRight(self,event=None):
        log.debug("Button Mid Right Pressed")
        if "MidRight" in self.functionDict:
            self.functionDict["MidRight"]()
    def ButtonTopRight(self,event=None):
        log.debug("Button Top Right Pressed")
        if "TopRight" in self.functionDict:
            self.functionDict["TopRight"]()
    def ButtonNext(self,event=None):
        log.debug("Button Next Pressed")
        if "Next" in self.functionDict:
            self.functionDict["Next"]()
    def ButtonPrev(self,event=None):
        log.debug("Button Prev Pressed")
        if "Prev" in self.functionDict:
            self.functionDict["Prev"]()

    def Button0(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["0"]()
        else:
            self.typeChar("0")
    def Button1(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["1"]()
        else:
            self.typeChar("1")
    def Button2(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["2"]()
        else:
            self.typeChar("2")
    def Button3(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["3"]()
        else:
            self.typeChar("3")
    def Button4(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["4"]()
        else:
            self.typeChar("4")
    def Button5(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["5"]()
        else:
            self.typeChar("5")
    def Button6(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["6"]()
        else:
            self.typeChar("6")
    def Button7(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["7"]()
        else:
            self.typeChar("7")
    def Button8(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["8"]()
        else:
            self.typeChar("8")
    def Button9(self,event=None):
        if self.shortcutsActive:
            self.shortcutDict["9"]()
        else:
            self.typeChar("9")
    def ButtonClear(self,event=None):
        self.backspace()
    def ButtonEnter(self, event=None):
        if self.typingPos>=0:
            retStr = self.UI.typingInput.text()
            self.typingOff()
            # validity should be checked in the callback
            # as well as any feedback to the user
            self.typingCallback(retStr)
        else:
            if "Enter" in self.functionDict:
                self.functionDict["Enter"]()

    def connectUIButtons(self):
        self.UI.labelTopLeft.mousePressEvent = self.ButtonTopLeft
        self.UI.labelMidLeft.mousePressEvent = self.ButtonMidLeft
        self.UI.labelBottomLeft.mousePressEvent = self.ButtonBottomLeft
        self.UI.labelCenterLeft.mousePressEvent = self.ButtonCenterLeft
        self.UI.labelCenterMid.mousePressEvent = self.ButtonCenterMid
        self.UI.labelCenterRight.mousePressEvent = self.ButtonCenterRight
        self.UI.labelBottomRight.mousePressEvent = self.ButtonBottomRight
        self.UI.labelMidRight.mousePressEvent = self.ButtonMidRight
        self.UI.labelTopRight.mousePressEvent = self.ButtonTopRight

        # "debug" buttons
        self.UI.buttonPrev.clicked.connect(self.ButtonPrev)
        self.UI.buttonNext.clicked.connect(self.ButtonNext)
        self.UI.button0.clicked.connect(self.Button0)
        self.UI.button1.clicked.connect(self.Button1)
        self.UI.button2.clicked.connect(self.Button2)
        self.UI.button3.clicked.connect(self.Button3)
        self.UI.button4.clicked.connect(self.Button4)
        self.UI.button5.clicked.connect(self.Button5)
        self.UI.button6.clicked.connect(self.Button6)
        self.UI.button7.clicked.connect(self.Button7)
        self.UI.button8.clicked.connect(self.Button8)
        self.UI.button9.clicked.connect(self.Button9)
        self.UI.buttonClear.clicked.connect(self.ButtonClear)
        self.UI.buttonEnter.clicked.connect(self.ButtonEnter)

    def connectFunctions(self, fDict):
        self.functionDict = fDict

    def connectShortcutFunctions(self, fDict):
        self.shortcutDict = fDict

    def decodeButton(self, num, press=True):
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
        if press:
            buttonMap[num]()