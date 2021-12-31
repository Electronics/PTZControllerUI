import os
import socket
import subprocess
import sys
import time
import re
import traceback
import logging

import serial
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSignal, QObject, QThread, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QLabel, QGridLayout, QWidget, QPushButton, QGraphicsScene, QGraphicsRectItem, QListWidgetItem, QMainWindow
from PyQt5.uic import loadUi

from sony_visca.visca_ip_camera import ViscaIPCamera
from sony_visca.visca_commands import Command
from SerialControl import SerialControl

log = logging.getLogger("PiControl")
logging.basicConfig(level=logging.DEBUG)

multipleSpaceRegex = re.compile(r" {2,}")

def updateUI():
    QtWidgets.qApp.processEvents()
    QtWidgets.qApp.processEvents() # yes this is twice...

def padIPAddress(ip):
    octets = ip.split(".")
    if len(octets) != 4:
        raise ValueError("Invalid IP Address!")
    nOctets = [int(x) for x in octets]
    return "{:03d}.{:03d}.{:03d}.{:03d}".format(nOctets[0],nOctets[1],nOctets[2],nOctets[3])

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
        retStr = self.UI.typingInput.text()
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



class CameraPinger(QThread):
    cameraUpdate = pyqtSignal(tuple) # (name, status)
    cameras = {}
    cameraList = []
    index = 0
    _isRunning=True

    def __init__(self, ticker=None):
        QThread.__init__(self)
        self.setTerminationEnabled(True)
        self.ticker = ticker # UI element to see if it's still working
    def __del__(self):
        pass

    def setCameras(self,cameras):
        self.cameras = cameras
        self.cameraList = list(cameras)
        self.index = 0

    def stop(self):
        self._isRunning=False
        self.quit()
        self.wait()
        self.deleteLater()

    def run(self):
        print("Camera pinger Thread started")
        while self._isRunning:
            if len(self.cameraList)>0:
                #todo do the ping / camera check
                camera = self.cameras[self.cameraList[self.index]]
                cameraName = self.cameraList[self.index]
                #ip = camera.ip
                #DEBUG:
                ip = cameraName[cameraName.index("(")+1:cameraName.index(")")]

                if os.name=="nt":
                    response = subprocess.call(["ping", "-n", "1", "-w", "500", ip], stdout=subprocess.DEVNULL)
                else:
                    response = subprocess.call(["ping", "-c", "1", "-i", "0.5", ip], stdout=subprocess.DEVNULL)

                if response==0:
                    self.cameraUpdate.emit((cameraName, 1))
                else:
                    self.cameraUpdate.emit((cameraName, -1))

                self.index+=1
                if self.index>=len(self.cameraList):
                    self.index = 0
                if self.ticker:
                    self.ticker.setText(str(self.index))
            QtWidgets.qApp.processEvents()

            QThread.msleep(500)

class MainScreen(QMainWindow):
    uiUpdateTrigger = pyqtSignal(list) # for arbitrary UI updates from other threads (filthy!)

    def __init__(self):
        super().__init__()
        self.selectedCamera = None
        self.selectedCameraName = ""
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
        self.textView.hide()

        self.cameraListWidget.currentItemChanged.connect(self.changeSelectedCamera)

        self.homeScreen()

        self.serial = SerialControl()
        self.serial.uiSignal.connect(self.UISignalReceiver)
        self.serial.buttonPressSignal.connect(self.ButtonControl.decodeButton)
        self.serial.cameraControl.connect(self.doCameraCommand)
        self.serial.start()

        self.pinger = CameraPinger(self.ticker)
        self.pinger.cameraUpdate.connect(self.pingCameraCallback)
        # self.pinger.start()

        self.show()

        self.discoverCameras()
        self.nextCamera() # select a camera to start with please
        self.debug()

    def debug(self):
        temp = ViscaIPCamera("LaurieC3","192.168.0.68","DC:ED:84:A1:9A:77",simple_visca=True, port=1259)
        temp.initialise()
        self.cameras["LaurieC3"] = temp
        self.cameraListWidget.addItem(QListWidgetItem("LaurieC3"))
        # self.cameras = {"CAM1 (10.0.1.20) [SONY]": None,
        #                 "CAM2 - LAURIE (192.168.0.68) [CHINESE]": temp,
        #                 "CAM3 WOWEE (10.0.1.199)": None,
        #                 "CAM4 TROTT (10.0.1.25)": None}
        # for camName in self.cameras:
        #     self.cameraListWidget.addItem(QListWidgetItem(camName))
        self.pinger.setCameras(self.cameras)

    def popup(self, message,length=800):
        self.infoPopup.setText(message)
        self.infoPopup.show()
        updateUI()
        QTimer.singleShot(length,self.infoPopup.hide)

    def dialogBox(self,title, enterFunc, cancelFunc=None):
        # I use the input box as I can't be bothered to reconnect the enter and clear buttons
        def onSubmit(s):
            if s is not None:
                if enterFunc:
                    enterFunc()
            else:
                if cancelFunc:
                    cancelFunc()
        self.ButtonControl.input("",title,onSubmit)


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

    def pingCameraCallback(self, params):
        camera, status = params
        c = self.cameraListWidget.findItems(camera,QtCore.Qt.MatchExactly)
        if len(c)>0:
            cameraItem = c[0]
            if status<=0:
                cameraItem.setForeground(QtGui.QBrush(QtCore.Qt.red))
            #print("Ping camera callback:",camera,"status",status)
        else:
            print("[PingCallback] Unable to find camera")

    def doCameraCommand(self, command, **kwargs):
        """Perform a camera action on the active camera handling errors and removing disconnected cameras."""
        if not self.selectedCamera:
            log.warning("!! No cam active !!")
            return
        if not self.selectedCamera.is_connected:
            log.warning("Skipping camera command, not connected!")
            return
        if isinstance(command, Command):
            self.selectedCamera.queueCommands(command, override=False)
        else:
            self.selectedCamera.queueCommands(Command(command, **kwargs), override=False)

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
                camName = cam.name + " (" + cam.ip + ")"
                #todo: don't reinialise new cameras
                try:
                    cam.initialise()
                except socket.timeout:
                    # probably camera is on a different network
                    print("Failed to initialise camera",camName)
                print("Adding '",camName,"'")
                self.cameras[camName] = cam
                self.cameraListWidget.addItem(QListWidgetItem(camName))

        self.pinger.setCameras(self.cameras)

    def changeSelectedCamera(self):
        if self.selectedCamera and self.selectedCamera.is_connected:
            # todo: send all these on a different thread: or with new library and queueing it might be ok
            self.selectedCamera.queueCommands(Command(Command.PanTiltStop()), Command(Command.ZoomStop), Command(Command.FocusStop), override=True)

        cameraName = self.cameraListWidget.currentItem().text()
        print("Selected camera changed to",cameraName)
        self.labelInfo.setText(cameraName)
        self.selectedCamera = self.cameras[cameraName]
        self.selectedCameraName = cameraName

        #todo update positions frame stuff

    def nextCamera(self, increment=1):
        # increment allows for going backwards (-1) and other funky things
        print("Next camera")
        current = self.cameraListWidget.currentItem()
        cameraList = list(self.cameras)
        if not cameraList:
            return
        if current == None:
            next = cameraList[0]
        else:
            next = cameraList[(cameraList.index(current.text()) + increment) % len(cameraList)]
        nextItem = self.cameraListWidget.findItems(next,QtCore.Qt.MatchExactly)[0]
        self.cameraListWidget.setCurrentItem(nextItem)
        # self.changeSelectedCamera() # this gets called by the UI?

    def storePreset(self):
        def confirm(num):
            if num.strip() != "":
                num = int(num)
                self.popup("Storing Preset "+str(num))
                self.doCameraCommand(Command(Command.MemorySet(num)))
        self.ButtonControl.input("  ","Store Preset:",confirm)
    def recallPreset(self):
        def confirm(num):
            if num.strip() != "":
                num = int(num)
                self.popup("Recalling Preset "+str(num))
                self.doCameraCommand(Command(Command.MemoryRecall(num)))
        self.ButtonControl.input("  ","Recall Preset:",confirm)

    def isCameraAutoFocus(self):
        try:
            if self.selectedCamera.isAutoFocusEnabled:
                return True
            else:
                return False
        except AttributeError:
            return True

    def homeScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Network/Pi Config")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        if self.isCameraAutoFocus():
            self.labelCenterRight.setText("")
            self.labelBottomRight.setText("")
            self.labelMidRight.setText("")
            self.labelTopRight.setText("Auto Focus")
        else:
            self.labelCenterRight.setText("Push Focus")
            self.labelBottomRight.setText("Focus Far")
            self.labelMidRight.setText("Focus Near")
            self.labelTopRight.setText("Manual Focus")
        self.labelCurrentScreen.setText("Home")

        self.textView.hide()

        def toggleAutoFocus():
            if self.isCameraAutoFocus():
                log.info("Turning autofocus off")
                self.selectedCamera.isAutoFocusEnabled = False
                self.selectedCamera.queueCommands(Command(Command.ManualFocus))
                self.labelCenterRight.setText("Push Focus")
                self.labelBottomRight.setText("Focus Far")
                self.labelMidRight.setText("Focus Near")
                self.labelTopRight.setText("Manual Focus")
            else:
                log.info("Turning autofocus on")
                self.selectedCamera.isAutoFocusEnabled = True
                self.selectedCamera.queueCommands(Command(Command.AutoFocus))
                self.labelCenterRight.setText("")
                self.labelBottomRight.setText("")
                self.labelMidRight.setText("")
                self.labelTopRight.setText("Auto Focus")
        def focusNear():
            if not self.isCameraAutoFocus():
                self.selectedCamera.queueCommands(Command(Command.FocusNear))
                QTimer.singleShot(120, lambda:self.selectedCamera.queueCommands(Command(Command.FocusStop)))
        def focusFar():
            if not self.isCameraAutoFocus():
                self.selectedCamera.queueCommands(Command(Command.FocusFar))
                QTimer.singleShot(120, lambda: self.selectedCamera.queueCommands(Command(Command.FocusStop)))
        def focusPush():
            if not self.isCameraAutoFocus():
                self.selectedCamera.queueCommands(Command(Command.FocusOnePush))

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.cameraConfigScreen(),
            "BottomLeft": lambda: self.networkConfigScreen(),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "CenterRight": lambda: focusPush(),
            "BottomRight": lambda: focusFar(),
            "MidRight": lambda: focusNear(),
            "TopRight": lambda: toggleAutoFocus(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def cameraConfigScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Home Screen")
        self.labelBottomLeft.setText("Network/Pi Config")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("Home Camera")
        self.labelBottomRight.setText("Reset Camera")
        self.labelMidRight.setText("Set Camera Name")
        self.labelTopRight.setText("Set Camera IP")
        self.labelCurrentScreen.setText("Camera Config")

        self.textView.hide()

        def homeCamera():
            def onConfirm():
                if self.selectedCamera:
                    self.selectedCamera.queueCommands(Command(Command.PanTiltHome))
                    self.selectedCamera.queueCommands(Command(Command.ZoomPos(0)))
                    self.popup("Homing camera")
            self.dialogBox("Home camera - are you sure?",onConfirm)

        def changeIP():
            #todo get old ip
            def setSubnet(newSubnet):
                if newSubnet==None:
                    self.popup("Canceled",500)
                    return
                #todo: validate?
                #todo set the IP and subnet
                print("Changing camera IP/sub",self.selectedCameraName,"to",self._tempIPAddress,"/",newSubnet)
                self.selectedCamera.setIP(ip=self._tempIPAddress, netmask=newSubnet)
            def setIP(newip_):
                if newip_==None:
                    self.popup("Canceled",500)
                    return
                try:
                    socket.inet_aton(newip_)
                    #todo store ip somehow
                    self._tempIPAddress = newip_
                    if "172." in newip_[:4] or "169." in newip_[:4]:
                        newSubnet = "255.000.000.000"
                    else:
                        newSubnet = "255.255.255.000"
                    self.ButtonControl.input(newSubnet, "Camera Subnet Mask", setSubnet)
                except socket.error:
                    self.popup("Invalid IP Address!")
                    return
            self.ButtonControl.input(padIPAddress(self.selectedCamera.ip),"Camera IP",setIP)

        def changeName():
            #todo get old name
            def setName(newName):
                if newName==None or newName=="":
                    self.popup("Canceled",500)
                    return
                # todo set name
                print("Changing camera name", self.selectedCamera.name, "to",newName)
            self.ButtonControl.input(self.selectedCamera.name,"Camera Name",setName)

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.homeScreen(),
            "BottomLeft": lambda: self.networkConfigScreen(),
            "MidRight": lambda: changeName(),
            "TopRight": lambda: changeIP(),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "CenterRight": lambda: homeCamera(),
            "BottomRight": lambda: self.selectedCamera.queueCommands(Command(Command.PanTiltReset,skipCompletion=True)),
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

        self.textView.show()

        def getPrimaryIP():
            # from https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # doesn't even have to be reachable
                s.connect(('10.255.255.255', 1))
                IP = s.getsockname()[0]
            except Exception:
                IP = '127.0.0.1'
            finally:
                s.close()
            return IP

        ip = getPrimaryIP()

        if os.name=="nt":
            interfaces=subprocess.check_output("netsh interface ipv4 show config").split(b"\r\n\r\n")
            interface = multipleSpaceRegex.sub(" ",[str(x,"utf-8") for x in interfaces if ip in str(x)][0].strip())
        elif os.name=="posix":
            interface = subprocess.check_output("ip a")
        else:
            interface = ""


        self.textView.setText("Network IP: "+ip+"\n"+
                              "Found Cameras: "+str(len(self.cameras))+"\n"+
                              "Missing Cameras: "+"0"+"\n"+
                              "FrontPanel Connected: "+str(self.serial.isConnected())+"\n"+
                              "\n"+
                              interface
                              )

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
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        print("Closing serial threads...")
        self.serial.stop()
        print("Stopping camera pinger")
        self.pinger.stop()
        log.info("Stopping cameras")
        for camName, cam in self.cameras.items():
            cam.close()
        print("Exiting")
        a0.accept()

if __name__ == '__main__':
    app = QApplication([])
    app.setStyle("Fusion")
    mainUI = MainScreen()
    sys.exit(app.exec())