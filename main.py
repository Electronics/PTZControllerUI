import socket
import sys
import time
import re
import traceback

import serial
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import pyqtSignal, QObject, QThread, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QLabel, QGridLayout, QWidget, QPushButton, QGraphicsScene, QGraphicsRectItem, QListWidgetItem, QMainWindow
from PyQt5.uic import loadUi

from visca_ip_camera import ViscaIPCamera
from visca_commands import Commands

SERIAL_PORT = "COM7"

serialRegex = re.compile(r"(?P<command>[A-Z]+)(?P<num0>-?[0-9]+)?(,(?P<num1>-?[0-9]+)(,(?P<num2>-?[0-9]+),(?P<num3>-?[0-9]+),(?P<num4>-?[0-9]+),(?P<num5>-?[0-9]+)(,(?P<num6>-?[0-9]+),(?P<num7>-?[0-9]+),(?P<num8>-?[0-9]+))?)?)?")

def updateUI():
    QtWidgets.qApp.processEvents()
    QtWidgets.qApp.processEvents() # yes this is twice...

class ButtonControl(QObject):
    functionDict = {} # a way of dynamically changing what the buttons do in a nice-ish way
    def __init__(self, parent):
        super().__init__()
        self.UI = parent

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
        if self.typingPos<0 or self.typingString=="":
            return
        self.typingString = self.typingString[:self.typingPos]+c+ self.typingString[self.typingPos+1:]
        self.typingPos += 1
        self.checkTypeSkip()
        self.typingUpdate()

    def backspace(self):
        if self.typingPos==0:
            self.typingCallback(None)
            self.typingOff()
        if self.typingPos<=0 or self.typingString=="" or self.typingStringOriginal=="":
            return
        self.checkTypeSkip(-1)
        self.typingPos -= 1
        self.typingString = self.typingString[:self.typingPos] + self.typingStringOriginal[self.typingPos] + self.typingString[self.typingPos + 1:]
        self.typingUpdate()

    def ButtonTopLeft(self,event=None):
        print("Button Top Left Pressed")
        if "TopLeft" in self.functionDict:
            self.functionDict["TopLeft"]()
    def ButtonMidLeft(self,event=None):
        print("Button Mid Left Pressed")
        if "MidLeft" in self.functionDict:
            self.functionDict["MidLeft"]()
    def ButtonBottomLeft(self,event=None):
        print("Button Bottom Left Pressed")
        if "BottomLeft" in self.functionDict:
            self.functionDict["BottomLeft"]()
    def ButtonCenterLeft(self,event=None):
        print("Button Center Left Pressed")
        if "CenterLeft" in self.functionDict:
            self.functionDict["CenterLeft"]()
    def ButtonCenterMid(self,event=None):
        print("Button Center Mid Pressed")
        if "CenterMid" in self.functionDict:
            self.functionDict["CenterMid"]()
    def ButtonCenterRight(self,event=None):
        print("Button Center Right Pressed")
        if "CenterRight" in self.functionDict:
            self.functionDict["CenterRight"]()
    def ButtonBottomRight(self,event=None):
        print("Button Bottom Right Pressed")
        if "BottomRight" in self.functionDict:
            self.functionDict["BottomRight"]()
    def ButtonMidRight(self,event=None):
        print("Button Mid Right Pressed")
        if "MidRight" in self.functionDict:
            self.functionDict["MidRight"]()
    def ButtonTopRight(self,event=None):
        print("Button Top Right Pressed")
        if "TopRight" in self.functionDict:
            self.functionDict["TopRight"]()
    def ButtonNext(self,event=None):
        print("Button Next Pressed")
        if "Next" in self.functionDict:
            self.functionDict["Next"]()
    def ButtonPrev(self,event=None):
        print("Button Prev Pressed")
        if "Prev" in self.functionDict:
            self.functionDict["Prev"]()

    def Button0(self,event=None):
        self.typeChar("0")
    def Button1(self,event=None):
        self.typeChar("1")
    def Button2(self,event=None):
        self.typeChar("2")
    def Button3(self,event=None):
        self.typeChar("3")
    def Button4(self,event=None):
        self.typeChar("4")
    def Button5(self,event=None):
        self.typeChar("5")
    def Button6(self,event=None):
        self.typeChar("6")
    def Button7(self,event=None):
        self.typeChar("7")
    def Button8(self,event=None):
        self.typeChar("8")
    def Button9(self,event=None):
        self.typeChar("9")
    def ButtonClear(self,event=None):
        self.backspace()
    def ButtonEnter(self, event=None):
        retStr = self.typingString
        self.typingOff()
        # validity should be checked in the callback
        # as well as any feedback to the user
        self.typingCallback(retStr)

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

class SerialControl(QThread):
    buttonPressSignal = pyqtSignal(int)
    buttonReleaseSignal = pyqtSignal(int)
    uiSignal = pyqtSignal(list)

    port = None
    learning = False

    def initPort(self):
        try:
            self.port = serial.Serial(SERIAL_PORT, 115200)

            self.port.write(b'HELLO\n')
        except serial.SerialException:
            print("Failed to open serial port")
    def __init__(self):
        QThread.__init__(self)
        self.initPort()
    def __del__(self):
        self.port.close()
        self.wait()

    def run(self):
        print("Serial Thread started")
        if not self.port or not self.port.is_open:
            print("Serial port not found, aborting external control")
            return
        while True:
            try:
                while True:
                    data = self.port.readline().decode("utf-8").strip()
                    dataSplit = serialRegex.search(data)
                    print("Serial data:",data)
                    command = dataSplit["command"]
                    try:
                        if command=="X":
                            x = int(dataSplit["num0"])
                            print("X position",x)
                        elif command=="Y":
                            y = int(dataSplit["num0"])
                            print("Y position",y)
                        elif command=="Z":
                            z = int(dataSplit["num0"])
                            print("Z position",z)
                        elif command=="P":
                            button = int(dataSplit["num0"])*8 + int(dataSplit["num1"])
                            print("Button Press",button)
                            self.buttonPressSignal.emit(button)
                        elif command=="R":
                            button = int(dataSplit["num0"]) * 8 + int(dataSplit["num1"])
                            print("Button Release",button)
                        elif command=="BOOT":
                            restX = int(dataSplit["num0"])
                            restY = int(dataSplit["num1"])
                            restZ = int(dataSplit["num2"])
                            stepX = int(dataSplit["num3"])
                            stepY = int(dataSplit["num4"])
                            stepZ = int(dataSplit["num5"])
                            print("uC is Booting",restX,restY,restZ,stepX,stepY,stepZ)
                        elif command=="LRN":
                            rawX = int(dataSplit["num0"])
                            rawY = int(dataSplit["num1"])
                            rawZ = int(dataSplit["num2"])
                            minX = int(dataSplit["num3"])
                            minY = int(dataSplit["num4"])
                            minZ = int(dataSplit["num5"])
                            maxX = int(dataSplit["num6"])
                            maxY = int(dataSplit["num7"])
                            maxZ = int(dataSplit["num8"])
                            print("Learning mode",data)
                            self.uiSignal.emit(["detailedPopupDetails","setText","X:%d Y:%d Z:%d\nminX:%d minY:%d minZ:%d\nmaxX:%d maxY:%d maxZ:%d"%(rawX,rawY,rawZ,minX,minY,minZ,maxX,maxY,maxZ)])
                            if not self.learning:
                                self.learning = True
                                self.uiSignal.emit(["detailedPopupTitle","setText","Joystick Calibration: Move the joystick to all maximum limits, center to home and then press continue"])
                                self.uiSignal.emit(["detailedPopup","show"])
                        elif command=="HOME":
                            print("Learning home")
                            self.uiSignal.emit(["detailedPopupDetails", "setText", "Learning Home Position..."])
                        elif command=="FIN":
                            restX = int(dataSplit["num0"])
                            restY = int(dataSplit["num1"])
                            restZ = int(dataSplit["num2"])
                            stepX = int(dataSplit["num3"])
                            stepY = int(dataSplit["num4"])
                            stepZ = int(dataSplit["num5"])
                            print("Learning finished",restX,restY,restZ,stepX,stepY,stepZ)
                            self.learning = False
                            self.uiSignal.emit(["detailedPopup","hide"])
                            self.uiSignal.emit(["popup","Cal Done!"])
                        else:
                            print("Unknown serial data:",data)
                    except IndexError:
                        print("Index error in decode")

            except:
                print("Ahhh EXCEPPPTIONN")
                print(traceback.format_exc())
                self.port.close()
                self.initPort()


class MainScreen(QMainWindow):
    uiUpdateTrigger = pyqtSignal(list) # for arbitrary UI updates from other threads (filthy!)

    def __init__(self):
        super().__init__()
        self.selectedCamera = None
        self.cameras = {}

        loadUi("MainUI.ui", self)
        self.ButtonControl = ButtonControl(self)
        self.ButtonControl.connectUIButtons()
        self.uiUpdateTrigger.connect(self.UISignalReceiver)

        self.setWindowTitle("PTZ Controller")
        camPosScene = QGraphicsScene(self)
        self.graphicsView.setScene(camPosScene)
        self.camPosRect = QGraphicsRectItem(QtCore.QRectF(0, 0, 5, 5))
        self.camPosRect.setBrush(QColor(255, 0, 0))
        self.camPosRect.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        camPosScene.addItem(self.camPosRect)

        self.infoPopup.hide()
        self.typingFrame.hide()
        self.detailedPopup.hide()

        self.cameraListWidget.currentItemChanged.connect(self.changeSelectedCamera)

        self.homeScreen()

        self.serial = SerialControl()
        self.serial.uiSignal.connect(self.UISignalReceiver)
        self.serial.buttonPressSignal.connect(self.ButtonControl.decodeButton)
        self.serial.start()

        self.show()

        self.discoverCameras()
        self.debug()

    def debug(self):
        self.cameras = {"CAM1 (10.0.1.20) [SONY]": None,
                        "CAM2 - LAURIE (10.0.1.999) [CHINESE]": None,
                        "CAM3 WOWEE (10.0.1.342)": None,
                        "CAM4 TROTT (10.0.1.65)": None}
        for camName in self.cameras:
            self.cameraListWidget.addItem(QListWidgetItem(camName))

    def popup(self, message,length=800):
        self.infoPopup.setText(message)
        self.infoPopup.show()
        updateUI()
        QTimer.singleShot(length,self.infoPopup.hide)

    def UISignalReceiver(self, data):
        # for sending signals that can update arbitrary parts of the UI
        if data and data[0]=="popup":
            if len(data)>2:
                self.popup(data[1],data[2])
            else:
                self.popup(data[1])
        elif len(data)>=4:
            data[3](getattr(getattr(self, data[0]), data[1])(data[2]))
        elif len(data)==3:
            getattr(getattr(self, data[0]), data[1])(data[2])
        elif len(data)==2:
            getattr(getattr(self, data[0]), data[1])()
        else:
            print("Invalid UISignal:",data)

    def drawCameraPos(self):
        self.camPosRect #todo: do something with this
        pass

    def discoverCameras(self):
        #todo close socket connections (and stop any cameras moving)
        self.cameras = {} # todo: remember lost cameras?
        #todo move this crap to a thread
        self.infoPopup.setText("Searching...")
        self.infoPopup.show()
        updateUI()
        print("Searching for cameras")
        found = ViscaIPCamera.discoverCameras()
        print("Found", len(found),"cameras")
        updateUI()
        self.infoPopup.setText("Found "+str(len(found))+" cameras") #todo make this popup appear for a second or something
        updateUI()
        QTimer.singleShot(500, self.infoPopup.hide)

        if found:
            for cam in found:
                #todo: don't reinialise new cameras
                cam.initialise()
                camName = cam.name+" ("+cam.ip+")"
                print("Adding '",camName,"'")
                self.cameras[camName] = cam
                self.cameraListWidget.addItem(QListWidgetItem(camName))

        # self.cameraListWidget.item(1).setForeground(QColor(255,0,0))

    def changeSelectedCamera(self):
        cameraName = self.cameraListWidget.currentItem().text()
        print("Selected camera changed to",cameraName)
        self.labelInfo.setText(cameraName)
        self.selectedCamera = self.cameras[cameraName]

        #todo update positions frame stuff
        #todo stop camera moving in any way if we were controlling it before switching

    def nextCamera(self, increment=1):
        # increment allows for going backwards (-1) and other funky things
        current = self.cameraListWidget.currentItem()
        cameraList = list(self.cameras)
        if current == None:
            next = cameraList[0]
        else:
            next = cameraList[(cameraList.index(current.text()) + increment) % len(cameraList)]
        nextItem = self.cameraListWidget.findItems(next,QtCore.Qt.MatchExactly)[0]
        self.cameraListWidget.setCurrentItem(nextItem)

    def homeScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Network Config")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("")
        self.labelBottomRight.setText("Focus Far")
        self.labelMidRight.setText("Focus Near")
        self.labelTopRight.setText("Auto/Manual Focus")
        self.labelCurrentScreen.setText("Home")

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.cameraConfigScreen(),
            "BottomLeft": lambda: self.networkConfigScreen(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def cameraConfigScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Home Screen")
        self.labelBottomLeft.setText("Network Config")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("")
        self.labelBottomRight.setText("Reset Camera")
        self.labelMidRight.setText("Set Camera Name")
        self.labelTopRight.setText("Set Camera IP")
        self.labelCurrentScreen.setText("Camera Config")

        def changeIP():
            #todo get old ip
            def setSubnet(newSubnet):
                if newSubnet==None:
                    self.popup("Canceled",500)
                    return
                #todo: validate?
                #todo set the IP and subnet
                print("Changing camera IP/sub","...","to","TODO","/",newSubnet)
            def setIP(newip_):
                if newip_==None:
                    self.popup("Canceled",500)
                    return
                try:
                    socket.inet_aton(newip_)
                    #todo store ip somehow
                    if "172." or "169." in newip_[:4]:
                        newSubnet = "255.000.000.000"
                    else:
                        newSubnet = "255.255.255.000"
                    self.ButtonControl.input(newSubnet, "Camera Subnet Mask", setSubnet)
                except socket.error:
                    self.popup("Invalid IP Address!")
                    return
            self.ButtonControl.input("010.000.001.123","Camera IP",setIP)

        def changeName():
            #todo get old name
            def setName(newName):
                if newName==None or newName=="":
                    self.popup("Canceled",500)
                    return
                # todo set name
                print("Changing camera name", "...", "to",newName)
            self.ButtonControl.input("OLDNAMEHERE","Camera Name",setName)

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.homeScreen(),
            "BottomLeft": lambda: self.networkConfigScreen(),
            "MidRight": lambda: changeName(),
            "TopRight": lambda: changeIP(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def networkConfigScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Home Screen")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("")
        self.labelBottomRight.setText("")
        self.labelMidRight.setText("")
        self.labelTopRight.setText("Set Ras-Pi IP")
        self.labelCurrentScreen.setText("Ras-Pi Network Config")

        # this is to change the PI'S network, not a camera!!
        def changeIP():
            #todo get old ip
            def setSubnet(newSubnet):
                if newSubnet==None:
                    self.popup("Canceled",500)
                    return
                #todo: validate?
                #todo set the IP and subnet
                print("Changing raspberry pi IP/sub","...","to","TODO","/",newSubnet)
            def setIP(newip_):
                if newip_==None:
                    self.popup("Canceled",500)
                    return
                try:
                    socket.inet_aton(newip_)
                    #todo store ip somehow
                    if "172." or "169." in newip_[:4]:
                        newSubnet = "255.000.000.000"
                    else:
                        newSubnet = "255.255.255.000"
                    self.ButtonControl.input(newSubnet, "RasPi Subnet Mask", setSubnet)
                except socket.error:
                    self.popup("Invalid IP Address!")
                    return
            self.ButtonControl.input("010.000.001.123","RasPi IP",setIP)

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.cameraConfigScreen(),
            "BottomLeft": lambda: self.homeScreen(),
            "TopRight": lambda: changeIP(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

if __name__ == '__main__':
    app = QApplication([])
    app.setStyle("Fusion")
    mainUI = MainScreen()
    sys.exit(app.exec())