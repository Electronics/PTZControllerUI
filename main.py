import time

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QLabel, QGridLayout, QWidget, QPushButton, QGraphicsScene, QGraphicsRectItem, QListWidgetItem
from PyQt5.uic import loadUi

from visca_ip_camera import ViscaIPCamera
from visca_commands import Commands

app = QApplication([])

def updateUI():
    QtWidgets.qApp.processEvents()
    QtWidgets.qApp.processEvents() # yes this is twice...

class ButtonControl(QObject):
    functionDict = {} # a way of dynamically changing what the buttons do in a nice-ish way
    def __init__(self, parent):
        super().__init__()
        self.UI = parent

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
        self.UI.buttonPrev.clicked.connect(self.ButtonPrev)
        self.UI.buttonNext.clicked.connect(self.ButtonNext)

    def connectFunctions(self, fDict):
        self.functionDict = fDict


class MainScreen(QWidget):
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

        self.cameraListWidget.currentItemChanged.connect(self.changeSelectedCamera)

        self.homeScreen()

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

    def UISignalReceiver(self, data):
        # for sending signals that can update arbitrary parts of the UI
        if len(data)>=4:
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
        time.sleep(0.5)
        self.infoPopup.hide()

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

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.homeScreen(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

if __name__ == '__main__':
    app.setStyle("Fusion")
    mainUI = MainScreen()
    app.exec()