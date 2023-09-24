import os
import socket
import sqlite3
import subprocess
import sys
import re
import logging
import time

from getmac import get_mac_address

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import QApplication, QGraphicsScene, QGraphicsRectItem, QListWidgetItem, QMainWindow, QFrame, QLabel, QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout, QGridLayout
from PyQt5.uic import loadUi

import database
from ButtonControl import ButtonControl
from CameraPinger import CameraPinger
from sony_visca.visca_ip_camera import ViscaIPCamera
from sony_visca.visca_commands import Command, Inquiry, Lookups
from SerialControl import SerialControl


logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("PiControl")
log.setLevel(logging.DEBUG)


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


def highlightButton(b, buttons):
    for i in range(len(buttons)):
        if buttons[i] is not None:
            buttons[i].setProperty("active", bool(i == b))
            buttons[i].style().unpolish(buttons[i])  # force stylesheet update?
            buttons[i].style().polish(buttons[i])

def styleButtons(buttons):
    for i in range(len(buttons)):
        if buttons[i] is not None:
            buttons[i].setStyleSheet("""
                    QPushButton[active="true"] {background-color: DarkGreen};
                    QPushButton[active="false"] {background-color: Grey};
                    """)
            buttons[i].setFont(QFont("MS Shell Dlg 2", 14))

class MainScreen(QMainWindow):
    uiUpdateTrigger = pyqtSignal(list) # for arbitrary UI updates from other threads (filthy!)

    def __init__(self):
        super().__init__()
        self.selectedCamera = None
        self.selectedCameraName = ""
        self.cameras = {}

        self.tempUI = [] # list in which to store temporary UI items that need to be removed on a page change

        loadUi("MainUI.ui", self)
        self.ButtonControl = ButtonControl(self)
        self.ButtonControl.connectUIButtons()
        self.uiUpdateTrigger.connect(self.UISignalReceiver)
        def presetRecallShortcut(presetNum):
            self.popup("Recalling Preset "+str(presetNum))
            self.doCameraCommand(Command.MemoryRecall(presetNum))
        self.ButtonControl.connectShortcutFunctions({
            "0": lambda: presetRecallShortcut(0),
            "1": lambda: presetRecallShortcut(1),
            "2": lambda: presetRecallShortcut(2),
            "3": lambda: presetRecallShortcut(3),
            "4": lambda: presetRecallShortcut(4),
            "5": lambda: presetRecallShortcut(5),
            "6": lambda: presetRecallShortcut(6),
            "7": lambda: presetRecallShortcut(7),
            "8": lambda: presetRecallShortcut(8),
            "9": lambda: presetRecallShortcut(9)
        })

        self.buttonRefresh.mouseReleaseEvent = lambda event: self.updateCameraProperties(full=True)

        self.setWindowTitle("PTZ Controller")
        self.camPosScene = QGraphicsScene(self)
        self.camPosScene.setSceneRect(QtCore.QRectF(self.graphicsView.rect())) # don't allow the scene to scroll / be bigger than the view
        self.graphicsView.setScene(self.camPosScene)
        self.camPosRect = QGraphicsRectItem(QtCore.QRectF(0, 0, 10, 10))
        self.camPosRect.setBrush(QColor(255, 0, 0))
        self.camPosRect.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.camPosRect.mouseMoveEvent = self.camPosRectMoveEvent
        self.camPosRect.mouseReleaseEvent = self.centerCamPosRect # TODO: add release of pan/tilt camera control
        self.camPosScene.addItem(self.camPosRect)
        self.centerCamPosRect()

        self.camPosRef = QGraphicsRectItem(QtCore.QRectF(0, 0, 1, 1))
        self.camPosRef.setPos(self.camPosScene.width() / 2 - self.camPosRef.rect().width()/2, self.camPosScene.height() / 2 - self.camPosRef.rect().height()/2)
        self.camPosScene.addItem(self.camPosRef)

        self.sliderX.setMinimum(-5120)
        self.sliderX.setMaximum(5120)
        self.sliderX.setValue(0)

        self.sliderY.setMinimum(-1280)
        self.sliderY.setMaximum(1280)
        self.sliderY.setValue(0)

        self.sliderZoomControl.valueChanged.connect(self.camZoomControl)
        self.sliderZoomControl.sliderReleased.connect(self.camZoomControlRelease)

        self.infoPopup.hide()
        self.typingFrame.hide()
        self.detailedPopup.hide()
        self.textView.hide()
        self.buttonExtra.hide()

        self.cameraListWidget.currentItemChanged.connect(self.changeSelectedCamera)

        self.homeScreen()

        self.serial = SerialControl()
        self.serial.uiSignal.connect(self.UISignalReceiver)
        self.serial.buttonPressSignal.connect(self.ButtonControl.decodeButton)
        self.serial.buttonReleaseSignal.connect(self.ButtonControl.decodeButtonRelease)
        self.serial.cameraControl.connect(self.doCameraCommand)
        self.serial.start()

        self.pinger = CameraPinger(self.ticker, self.cameras)
        self.pinger.cameraUpdate.connect(self.pingCameraCallback)
        self.pinger.start()

        self.show()

        self.discoverCameras()
        # self.debug()
        self.nextCamera() # select a camera to start with please

    def camPosRectMoveEvent(self, event):
        super(QGraphicsRectItem, self.camPosRect).mouseMoveEvent(event)
        x = self.camPosRect.pos().x()-(self.camPosScene.width() / 2) + (self.camPosRect.rect().width())
        y = self.camPosRect.pos().y()-(self.camPosScene.height() / 2) + (self.camPosRect.rect().height())
        NUM_STAGES = 16
        x = min(max(int(x/(self.camPosScene.width()/2/(NUM_STAGES+1))),-NUM_STAGES),NUM_STAGES)
        y = -min(max(int(y/(self.camPosScene.height()/2/(NUM_STAGES+1))),-NUM_STAGES),NUM_STAGES)
        log.debug("Cam move: %d %d", x,y)

        # pass this through to the serial decoder which already has all the logic in it
        if hasattr(self, "serial"):
            self.serial.vx = x
            self.serial.vy = y
            self.serial.moveCam()

    def centerCamPosRect(self, *_):
        self.camPosRect.setPos((self.camPosScene.width() / 2) - (self.camPosRect.rect().width()/2), (self.camPosScene.height() / 2) - (self.camPosRect.rect().height()/2))
        x = self.camPosRect.pos().x() - (self.camPosScene.width() / 2) + (self.camPosRect.rect().width() / 2)
        y = self.camPosRect.pos().y() - (self.camPosScene.height() / 2) + (self.camPosRect.rect().height() / 2)
        log.debug("Center: %f %f", x, y)

        # pass this through to the serial decoder which already has all the logic in it
        if hasattr(self, "serial"):
            self.serial.vx = 0
            self.serial.vy = 0
            self.serial.moveCam()

    def camZoomControl(self):
        log.debug("Zoom Control: %d", self.sliderZoomControl.value())
        if hasattr(self, "serial"):
            self.serial.vz = self.sliderZoomControl.value()
            self.serial.moveCam()

    def camZoomControlRelease(self):
        log.debug("Zoom Control release")
        self.sliderZoomControl.setValue(0)
        if hasattr(self, "serial"):
            self.serial.vz = 0
            self.serial.moveCam()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        super(MainScreen, self).keyPressEvent(event)
        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            log.debug("Keyboard Escape pressed")
            self.ButtonControl.escape()
        elif key == QtCore.Qt.Key_Return or key == QtCore.Qt.Key_Enter:
            log.debug("Keyboard Enter pressed")
            self.ButtonControl.buttonEvent(10)

    def debug(self):
        temp = ViscaIPCamera("LaurieC3","192.168.0.68","DC:ED:84:A1:9A:77",simple_visca=True, port=1259)
        temp.initialise()
        self.cameras["LaurieC3 [192.168.0.68]"] = temp
        cameraItem = QListWidgetItem("LaurieC3 [192.168.0.68]")
        cameraItem.setData(QtCore.Qt.UserRole, temp)
        self.cameraListWidget.addItem(cameraItem)
        # self.cameras["LaurieC3 [TEST]"] = temp
        # self.cameraListWidget.addItem(QListWidgetItem("LaurieC3 [TEST]"))
        # self.cameras = {"CAM1 (10.0.1.20) [SONY]": None,
        #                 "CAM2 - LAURIE (192.168.0.68) [CHINESE]": temp,
        #                 "CAM3 WOWEE (10.0.1.199)": None,
        #                 "CAM4 TROTT (10.0.1.25)": None}
        # for camName in self.cameras:
        #     self.cameraListWidget.addItem(QListWidgetItem(camName))

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
            log.error("Invalid UISignal:",data)

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
            else:
                cameraItem.setForeground(QtGui.QBrush(QtCore.Qt.black))
            log.log(0,"Ping camera callback: %s status %s",camera,status) # highest level of verbosity
        else:
            log.warning("[PingCallback] Unable to find camera")

    def doCameraCommand(self, command, **kwargs):
        """Perform a camera action on the active camera handling errors and removing disconnected cameras."""
        if not self.selectedCamera:
            log.warning("!! No cam active !!")
            return
        if not self.selectedCamera.is_connected:
            log.warning("Skipping camera command, not connected!")
            return
        if isinstance(command, Command):
            self.selectedCamera.queueCommands(command, override=True)
        else:
            self.selectedCamera.queueCommands(Command(command, **kwargs), override=True)

    def getManualCamerasFromdb(self):
        """Get camera objects from DB data"""
        rows = database.query("SELECT * FROM cameras WHERE autocreated = 0")
        extras = []
        for row in rows:
            if row["type"] == "sony":
                extras.append(ViscaIPCamera(row["name"], row["ip"], row["mac"])) # TODO: update mac?
            else:
                extras.append(ViscaIPCamera(row["name"], row["ip"], row["mac"], port=1259, simple_visca=True))
        log.info("Found %d extra cameras (from db)", len(extras))
        return extras

    def discoverCameras(self):
        self.infoPopup.setText("Searching...")
        self.infoPopup.show()
        updateUI()
        log.info("Searching for cameras")
        found = ViscaIPCamera.discoverCameras()
        found += ViscaIPCamera.discoverNonSony()
        #TODO: sometimes discovery can duplicate a camera, causing failure then in removing an already-removed item when re-generating the UI list
        log.info("Found %d cameras", len(found))
        updateUI()
        self.popup("Found "+str(len(found))+" cameras")

        if found:
            for cam in found:
                # database fun
                row = database.query("SELECT * FROM cameras WHERE mac = ?", (cam.mac,), one=True)
                if row:
                    # update it
                    log.debug("Updating camera[%s,%s] to database",cam.name, cam.ip)
                    database.query(
                        "UPDATE cameras SET name = ?, type = ?, ip = ?, autocreated = 1 WHERE mac = ?",
                        (cam.name, "sony", cam.ip, cam.mac),
                    )
                    # Set the display name of the camera if set in db
                    if row["display_name"]:
                        cam.name = row["display_name"]
                else:
                    # Create it
                    log.debug("Adding new camera[%s,%s] to database", cam.name, cam.ip)
                    database.query(
                        "INSERT INTO cameras (name, ip, type, mac, autocreated) VALUES (?, ?, ?, ?, 1)",
                        (cam.name, cam.ip, "sony", cam.mac),
                    )
                database.commit()

        found += self.getManualCamerasFromdb()
        database.close()

        known_ips = [c.ip for k, c in self.cameras.items()] # old list of ips
        known_names = list(self.cameras.keys()) # old list of cam names
        # no clearing as we find the previous found cameras and update them
        #TODO: clear out old cameras that are properly gone
        #self.cameras.clear()  # do NOT re-initialise as we've passed a reference to other bits
        notFound = list(self.cameras.keys()) # we'll remove cameras as we find them, anything left we need to remove
        stuckCameras = [i.text() for i in self.cameraListWidget.findItems('.*', QtCore.Qt.MatchRegExp)] # bodge to remove stuck cameras in list widget

        if found:
            for cam in found:
                if cam.ip not in known_ips:
                    try:
                        cam.initialise()
                        self.updateCameraProperties(camera=cam)
                    except socket.timeout:
                        # probably camera is on a different network
                        log.warning("Failed to initialise camera %s",str(cam))
                    log.info("Adding '%s'",str(cam))
                    self.cameras[str(cam)] = cam

                    cameraItem = QListWidgetItem(str(cam))
                    cameraItem.setData(QtCore.Qt.UserRole, cam)
                    self.cameraListWidget.addItem(cameraItem)

                else:
                    # camera already existed (presumably)
                    oldName = known_names[known_ips.index(cam.ip)]
                    self.cameras.pop(oldName)
                    if oldName in notFound: # in case there's a duplicate ip or something
                        notFound.remove(oldName)
                    if oldName in stuckCameras:
                        stuckCameras.remove(oldName)

                    self.cameras[str(cam)] = cam
                    items = self.cameraListWidget.findItems(oldName, QtCore.Qt.MatchExactly)
                    if len(items)==1:
                        items[0].setData(QtCore.Qt.UserRole, cam)
                    else:
                        log.error("Failed to find existing camera in QListWidget")

        # delete old cameras that have disappeared
        for camName in notFound:
            self.cameras.pop(camName)
            # find qlistwidget item
            item = self.cameraListWidget.findItems(camName, QtCore.Qt.MatchExactly)[0]
            index = self.cameraListWidget.row(item)
            self.cameraListWidget.takeItem(index)
            log.info("Removed missing camera %s",item.data(QtCore.Qt.UserRole))
            del item
        for cam in stuckCameras:
            items = self.cameraListWidget.findItems(cam, QtCore.Qt.MatchExactly)
            if len(items)>0:
                index = self.cameraListWidget.row(items[0])
                if index>=0:
                    self.cameraListWidget.takeItem(index)
                    log.info("Removed stuck camera %s",camName.text())


    def changeSelectedCamera(self):
        if self.selectedCamera and self.selectedCamera.is_connected:
            # todo: send all these on a different thread: or with new library and queueing it might be ok
            self.selectedCamera.queueCommands(Command(Command.PanTiltStop()), Command(Command.ZoomStop), Command(Command.FocusStop), override=True)

        try:
            currentItem = self.cameraListWidget.currentItem()
            if currentItem is not None:
                self.selectedCamera = currentItem.data(QtCore.Qt.UserRole)
                self.selectedCameraName = self.selectedCamera.name
                log.info("Selected camera changed to %s", self.selectedCameraName)
                self.labelInfo.setText(self.selectedCameraName)
            else:
                log.info("Attempted to change camera to selection which is None")
        except KeyError:
            log.warning("Tried to switch camera to a non-existent camera; has it been deleted?")

        #todo update positions frame stuff

    def nextCamera(self, increment=1):
        # increment allows for going backwards (-1) and other funky things
        log.info("Next camera" if increment>0 else "Prev camera")
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
            if num and num.strip() != "":
                num = int(num)
                self.popup("Storing Preset "+str(num))
                self.doCameraCommand(Command(Command.MemorySet(num)))
        self.ButtonControl.input("","Store Preset:",confirm)
    def recallPreset(self):
        def confirm(num):
            if num and num.strip() != "":
                num = int(num)
                self.popup("Recalling Preset "+str(num))
                self.doCameraCommand(Command(Command.MemoryRecall(num)))
        self.ButtonControl.input("","Recall Preset:",confirm)

    def updatePropertiesUI(self):
        def checkParameter(parameter):
            if self.selectedCamera is None:
                return None # this shouldn't occur but does...
            try:
                d = self.selectedCamera.properties.__dict__
                if parameter in d:
                    return d[parameter]
                else:
                    return None
            except AttributeError:
                self.selectedCamera.parameters = {}
            return None
        try:
            if checkParameter("iris") is not None:
                self.labelIris.setText(Lookups.Iris[self.selectedCamera.properties.iris])
            if checkParameter("gain") is not None:
                self.labelGain.setText(str(self.selectedCamera.properties.gain*3)+" dB")
            if checkParameter("shutter") is not None:
                self.labelShutter.setText(Lookups.Shutter[self.selectedCamera.properties.shutter])
            if checkParameter("zoom") is not None:
                self.sliderZoom.setValue(self.selectedCamera.properties.zoom)
            if checkParameter("focus") is not None:
                self.sliderFocus.setValue(self.selectedCamera.properties.focus)
            if checkParameter("exposureComp") is not None:
                self.labelExpComp.setText(str(self.selectedCamera.properties.exposureComp*1.5-10.5)+" dB")
            if checkParameter("pan") is not None:
                log.info("Pan: %d", self.selectedCamera.properties.pan)
                self.sliderX.setValue(self.selectedCamera.properties.pan)
            if checkParameter("tilt") is not None:
                log.info("Tilt: %d", self.selectedCamera.properties.tilt)
                self.sliderY.setValue(self.selectedCamera.properties.tilt)
        except KeyError:
            log.error("KeyError whilst looking up selected camera properties")

    def updateCameraProperties(self, camera=None, full=True, type=""):
        if camera is None:
            if self.selectedCamera is None:
                return
            camera = self.selectedCamera
        if type=="block" or full:
            camera.properties.decodeBlockControl(camera.inquire(Command(Inquiry.BlockControl)))
        if type=="blockOther" or full:
            camera.properties.decodeBlockOther(camera.inquire(Command(Inquiry.BlockOther)))
        if type=="blockEnlargement" or full:
            camera.properties.decodeBlockEnlargement1(camera.inquire(Command(Inquiry.BlockEnlargement)))
        if type=="" or full:
            camera.properties.decodeBlockLens(camera.inquire(Command(Inquiry.BlockLens)))  # TODO: seperate out the camera inquire and check if it actualy responded
            camera.properties.decodePanTiltPosition(camera.inquire(Command(Inquiry.PanTiltPos)))

        self.updatePropertiesUI()

    def toggleCameraProperty(self, parameter, qwidget, textTrue, textFalse, commandTrue=None, commandFalse=None, toggle=True, default=True):
        # toggles a parameter on a camera and/or checks what state the paramters is in and udpdates relevent bits
        if self.selectedCamera is None:
            return default

        def checkParameter(parameter):
            try:
                d = self.selectedCamera.properties.__dict__
                if parameter in d:
                    return d[parameter]
                else:
                    return default
            except AttributeError:
                self.selectedCamera.parameters = {}
            return default

        currentState = checkParameter(parameter)
        if toggle:
            if commandTrue is None or commandFalse is None:
                raise SyntaxError("Command missing from toggle parameter call!")
            currentState = not currentState

            self.doCameraCommand(commandTrue if currentState else commandFalse)
            self.selectedCamera.properties.__dict__[parameter] = currentState

        # update UI elements
        if currentState:
            qwidget.setText(textTrue)
        else:
            qwidget.setText(textFalse)

    def changeView(self, newViewFunc=None): # without a new view function, this can just clear popups
        self.textView.hide()
        self.buttonExtra.hide()
        for item in self.tempUI:
            item.setParent(None)
            item.deleteLater()
        self.tempUI.clear()
        if newViewFunc is not None:
            newViewFunc()

    def homeScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Settings")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("Extra Settings")
        self.labelBottomRight.setText("Iris")
        self.labelMidRight.setText("Shutter")
        self.labelTopRight.setText("Focus")
        self.labelCurrentScreen.setText("Home")

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "CenterRight": lambda: self.changeView(self.extraMenu),
            "BottomRight": lambda: self.changeView(self.irisScreen),
            "MidRight": lambda: self.changeView(self.shutterScreen),
            "TopRight": lambda: self.changeView(self.focusScreen),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def cameraConfigScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Home Screen")
        self.labelBottomLeft.setText("Settings")
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
            if not self.selectedCamera:
                log.info("No camera selected to change IP!")
                return
            #todo get old ip
            def setSubnet(newSubnet):
                if newSubnet==None:
                    self.popup("Canceled",500)
                    return
                #todo: validate?
                log.info("Changing camera IP/sub %s to %s/%s",self.selectedCameraName,self._tempIPAddress,newSubnet)
                try:
                    if self.selectedCamera:
                        self.selectedCamera.setIP(ip=self._tempIPAddress, netmask=newSubnet)
                except socket.timeout:
                    self.popup("Failed to set IP: timeout")
                    log.warning("Failed to set IP: timeout")
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
            if self.selectedCamera:
                def setName(newName):
                    if newName==None or newName=="":
                        self.popup("Canceled",500)
                        return
                    # todo set name
                    if self.selectedCamera:
                        self.selectedCamera.setIP(name=newName)
                    log.info(f"Changing camera name {self.selectedCamera.name} to {newName}")

                self.ButtonControl.input(self.selectedCamera.name,"Camera Name",setName)
            else:
                self.popup("No camera selected!")

        def PanTiltReset():
            if not self.selectedCamera:
                return
            self.selectedCamera.queueCommands(Command(Command.PanTiltReset, skipCompletion=True))

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.changeView(self.homeScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "MidRight": lambda: changeName(),
            "TopRight": lambda: changeIP(),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "CenterRight": lambda: homeCamera(),
            "BottomRight": lambda: PanTiltReset(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def networkConfigScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Home Screen")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("Reboot/Shutdown")
        if self.ButtonControl.isShortcutActive():
            self.labelBottomRight.setText("Preset Shortcuts On")
        else:
            self.labelBottomRight.setText("Preset Shortcuts Off")
        self.labelMidRight.setText("Calibrate Joystick")
        self.labelTopRight.setText("Add Manual Camera")
        self.labelCurrentScreen.setText("Settings")
        self.buttonExtra.setText("Remove Manual Camera")
        self.buttonExtra.show()

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
            try:
                interface = subprocess.check_output("ip a", shell=True)
            except subprocess.CalledProcessError:
                interface = ""
        else:
            interface = ""


        self.textView.setText("Network IP: "+str(ip)+"\n"+
                              "Found Cameras: "+str(len(self.cameras))+"\n"+
                              "Missing Cameras: "+"0"+"\n"+
                              "FrontPanel Connected: "+str(self.serial.isConnected())+"\n"+
                              "\n"+
                              str(interface)
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
                log.info("Changing raspberry pi IP/sub","...","to","TODO","/",newSubnet)
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

        def addCamera():
            def setName(newName):
                if newName == None or newName == "":
                    self.popup("Canceled", 500)
                    return

                def setIP(newip_):
                    if newip_ == None:
                        self.popup("Canceled", 500)
                        self.labelCenterMid.setText("Recall Preset")
                        self.ButtonControl.functionPressDict["CenterMid"] = lambda: self.storePreset()
                        return
                    try:
                        socket.inet_aton(newip_)

                        # search for the mac address (and the device itself)
                        # hopefully it responds to arp
                        mac = get_mac_address(ip=newip_)

                        if not mac:
                            self.popup("Failed to find device on network")
                        else:
                            # todo determine the type of camera
                            log.debug("Adding new camera: %s[%s,%s]", newName, newip_,mac)
                            cam = ViscaIPCamera(newName, newip_, mac, simple_visca=True if "#" in newName else False)
                            cam.initialise()
                            camItem = QListWidgetItem(str(cam))
                            camItem.setData(QtCore.Qt.UserRole, cam)
                            self.cameraListWidget.addItem(camItem)
                            self.cameras[str(cam)] = cam
                            log.debug("Adding new camera[%s,%s,%s] to database", newName, newip_,mac)
                            try:
                                database.query(
                                    "INSERT INTO cameras (name, ip, type, mac, autocreated) VALUES (?, ?, ?, ?, 0)",
                                    (newName, newip_, "chinese" if "#" in newName else "sony", mac),
                                )
                                database.commit()
                            except sqlite3.IntegrityError:
                                log.warning("Cannot add manual camera to database due to already-existing entry")
                            self.labelCenterMid.setText("Recall Preset")
                            self.ButtonControl.functionPressDict["CenterMid"] = lambda: self.storePreset()

                    except socket.error:
                        self.popup("Invalid IP Address!")
                        self.labelCenterMid.setText("Recall Preset")
                        self.ButtonControl.functionPressDict["CenterMid"] = lambda: self.storePreset()
                        return

                self.labelCenterMid.setText("•")
                self.ButtonControl.functionPressDict["CenterMid"] = lambda: self.ButtonControl.typeChar(".")
                self.ButtonControl.input("", "Camera IP", setIP)

            self.ButtonControl.input("", "Camera Name (# for simpleVisca)", setName)

        def removeCamera():
            try:
                database.query(
                    "DELETE FROM cameras WHERE name = ?",
                    (self.selectedCameraName,),
                )
                database.commit()
                self.popup(f"Sucesfully deleted {self.selectedCameraName}")
                deletingQItem = self.cameraListWidget.currentItem()
                index = self.cameraListWidget.row(deletingQItem)
                if index >= 0:
                    self.cameraListWidget.takeItem(index)
                self.cameras.pop(deletingQItem.text())
                log.info("Removed camera %s", deletingQItem.text())
            except sqlite3.IntegrityError:
                log.warning("Cannot remove camera")

        isCalibrating = False
        def calibrateJoystick():
            # send LEARN and LEARNOFF
            isCalibrating = True
            self.serial.sendCommand("LEARN")

        def finishCalibrate():
            isCalibrating = False
            self.serial.sendCommand("LEARNOFF")

        def swapShortcuts():
            if self.ButtonControl.isShortcutActive():
                self.ButtonControl.setShortcutActive(False)
                self.labelBottomRight.setText("Preset Shortcuts Off")
            else:
                self.ButtonControl.setShortcutActive(True)
                self.labelBottomRight.setText("Preset Shortcuts On")

        self.buttonExtra.clicked.connect(lambda: removeCamera())
        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.homeScreen),
            "BottomRight": lambda: swapShortcuts(),
            "MidRight": lambda: calibrateJoystick(),
            "TopRight": lambda: addCamera(),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "CenterRight": lambda: self.changeView(self.shutdownScreen),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
            "Enter": lambda: finishCalibrate()
        })

    def focusScreen(self):
        self.labelTopLeft.setText("Home Screen")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Settings")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("Push Focus")
        self.labelBottomRight.setText("Focus Far")
        self.labelMidRight.setText("Focus Near")
        self.labelCurrentScreen.setText("Focus Menu")

        self.toggleCameraProperty("autoFocus", self.labelTopRight, "Auto Focus", "Manual Focus", toggle=False)

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.changeView(self.homeScreen),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "CenterRight": lambda: self.doCameraCommand(Command.FocusOnePush),
            "BottomRight": lambda: self.doCameraCommand(Command.FocusFar),
            "MidRight": lambda: self.doCameraCommand(Command.FocusNear),
            "TopRight": lambda: self.toggleCameraProperty("autoFocus", self.labelTopRight, "Auto Focus", "Manual Focus", Command.AutoFocus, Command.ManualFocus),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        },{
            "BottomRight": lambda: self.doCameraCommand(Command.FocusStop),
            "MidRight": lambda: self.doCameraCommand(Command.FocusStop),
        })

    def shutterScreen(self):
        self.labelTopLeft.setText("Home Screen")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Settings")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("")
        self.labelBottomRight.setText("Longer (Down)")
        self.labelMidRight.setText("Shorter (Up)")
        self.labelTopRight.setText("Reset Shutter")
        self.labelCurrentScreen.setText("Shutter Speed")

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.changeView(self.homeScreen),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "BottomRight": lambda: self.doCameraCommand(Command.ShutterDown),
            "MidRight": lambda: self.doCameraCommand(Command.ShutterUp),
            "TopRight": lambda: self.doCameraCommand(Command.ShutterReset),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def irisScreen(self):
        self.labelTopLeft.setText("Home Screen")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Settings")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("")
        self.labelBottomRight.setText("Inc F-Stop")
        self.labelMidRight.setText("Dec F-Stop")
        self.labelTopRight.setText("Reset F-Stop")
        self.labelCurrentScreen.setText("Shutter Speed")

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.changeView(self.homeScreen),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "BottomRight": lambda: self.doCameraCommand(Command.IrisDown),
            "MidRight": lambda: self.doCameraCommand(Command.IrisUp),
            "TopRight": lambda: self.doCameraCommand(Command.IrisReset),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def apertureScreen(self):
        self.labelTopLeft.setText("Home Screen")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Settings")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("")
        self.labelBottomRight.setText("Down")
        self.labelMidRight.setText("Up")
        self.labelTopRight.setText("Reset")
        self.labelCurrentScreen.setText("Aperture (Gain?)")

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.changeView(self.homeScreen),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "BottomRight": lambda: self.doCameraCommand(Command.ApertureDown),
            "MidRight": lambda: self.doCameraCommand(Command.ApertureUp),
            "TopRight": lambda: self.doCameraCommand(Command.ApertureReset),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def expCompScreen(self):
        self.labelTopLeft.setText("Home Screen")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Settings")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("Reset")
        self.labelBottomRight.setText("Down")
        self.labelMidRight.setText("Up")

        self.labelCurrentScreen.setText("Exposure Compensation")

        self.toggleCameraProperty("exposureCompOn", self.labelTopRight, "ExpComp On", "ExpComp Off", toggle=False)

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.changeView(self.homeScreen),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "CenterRight": lambda: self.doCameraCommand(Command.ExposureCompReset),
            "BottomRight": lambda: self.doCameraCommand(Command.ExposureCompDown),
            "MidRight": lambda: self.doCameraCommand(Command.ExposureCompUp),
            "TopRight": lambda: self.toggleCameraProperty("exposureCompOn", self.labelTopRight, "ExpComp On", "ExpComp Off", Command.ExposureCompOn, Command.ExposureCompOff),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def gainScreen(self):
        self.labelTopLeft.setText("Home Screen")
        self.labelMidLeft.setText("Camera Config")
        self.labelBottomLeft.setText("Settings")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("")
        self.labelBottomRight.setText("Down")
        self.labelMidRight.setText("Up")
        self.labelTopRight.setText("Reset")
        self.labelCurrentScreen.setText("Gain")

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.changeView(self.homeScreen),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "BottomRight": lambda: self.doCameraCommand(Command.GainDown),
            "MidRight": lambda: self.doCameraCommand(Command.GainUp),
            "TopRight": lambda: self.doCameraCommand(Command.GainReset),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def extraMenu(self):
        cancelFrame = QFrame()
        cancelFrame.resize(self.size())
        cancelFrame.mousePressEvent = lambda e: self.changeView()
        self.layout().addWidget(cancelFrame)
        self.tempUI.append(cancelFrame)

        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setFrameShadow(QFrame.Raised)
        frame.setLineWidth(5)
        frame.setAutoFillBackground(True)
        layout = QVBoxLayout()
        buttonFrame = QFrame()
        buttonLayout = QGridLayout()
        buttonFrame.setLayout(buttonLayout)
        buttonFrame.setFont(QFont("MS Shell Dlg 2", 14))
        frame.setLayout(layout)
        title = QLabel("Extra Settings")
        title.setFont(QFont("MS Shell Dlg 2", 20))
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(buttonFrame)

        self.updateCameraProperties()

        buttonExposure = QPushButton("\nExposure\n\n")
        buttonExposure.clicked.connect(lambda event: buttonCallback("exposure"))
        buttonWhiteBalance = QPushButton("\nWhite\nBalance\n")
        buttonWhiteBalance.clicked.connect(lambda event: buttonCallback("whitebalance"))
        buttonExpComp = QPushButton("\nExposure\nCompensation\n")
        buttonExpComp.clicked.connect(lambda event: buttonCallback("expcomp"))
        buttonGain = QPushButton("\nGain\n\n")
        buttonGain.clicked.connect(lambda event: buttonCallback("gain"))
        buttonBacklight = QPushButton("\nBacklight\nComp On\n")
        self.toggleCameraProperty("backlightComp", buttonBacklight, "\nBacklight\nComp On\n", "\nBacklight\nComp Off\n", toggle=False)
        buttonBacklight.clicked.connect(lambda event: buttonCallback("backlight"))
        buttonDynamicRange = QPushButton("\nWide Dynamic\n\n")
        buttonDynamicRange.clicked.connect(lambda event: buttonCallback("dynamicrange"))
        buttonAperture = QPushButton("\nAperture\n(Gain?)\n")
        buttonAperture.clicked.connect(lambda event: buttonCallback("aperture"))
        buttonHighRes = QPushButton("\nHigh Resolution\nOn\n")
        buttonHighRes.clicked.connect(lambda event: buttonCallback("highres"))
        buttonNoiseReduction = QPushButton("\nNoise Reduction\n\n")
        buttonNoiseReduction.clicked.connect(lambda event: buttonCallback("noisereduction"))
        buttonHighSensitivity = QPushButton("\nHigh Sensitivity\nOn\n")
        self.toggleCameraProperty("highSensitivity", buttonHighSensitivity, "\nHigh Sensitivity\nOn\n", "\nHigh Sensitivity\nOff\n", toggle=False)
        buttonHighSensitivity.clicked.connect(lambda event: buttonCallback("highsensitivity"))
        buttonInfoDisplay = QPushButton("\nInfo Display\nOff\n")
        buttonInfoDisplay.clicked.connect(lambda event: buttonCallback("infodisp"))
        buttonLayout.addWidget(buttonExposure,0,0)
        buttonLayout.addWidget(buttonWhiteBalance,0,1)
        buttonLayout.addWidget(buttonExpComp,0,2)
        buttonLayout.addWidget(buttonGain,0,3)
        buttonLayout.addWidget(buttonBacklight,1,0)
        buttonLayout.addWidget(buttonDynamicRange,1,1)
        buttonLayout.addWidget(buttonAperture,1,2)
        buttonLayout.addWidget(buttonHighRes,1,3)
        buttonLayout.addWidget(buttonNoiseReduction,2,0)
        buttonLayout.addWidget(buttonHighSensitivity,2,1)
        buttonLayout.addWidget(buttonInfoDisplay,2,2)

        def buttonCallback(button):
            # seperate callback function rather than lambdas as often in duplciates of this menu we want to run a command AND close the popup
            if button == "exposure":
                self.changeView(self.exposureMenu)
            elif button == "whitebalance":
                self.changeView(self.whitebalanceMenu)
            elif button == "expcomp":
                self.changeView(self.expCompScreen)
            elif button == "gain":
                self.changeView(self.gainScreen)
            elif button == "backlight":
                self.toggleCameraProperty("backlightComp", buttonBacklight, "\nBacklight\nComp On\n", "\nBacklight\nComp Off\n", Command.BacklightCompOn, Command.BacklightCompOff)
            elif button == "dynamicrange":
                self.changeView(self.dynamicRangeMenu)
            elif button == "aperture":
                self.changeView(self.apertureScreen)
            elif button == "highres":
                self.toggleCameraProperty("highResolution", buttonHighRes, "\nHigh Resolution\nOn\n", "\nHigh Resolution\nOff\n", Command.HighResolutionOn, Command.HighResolutionOff)
            elif button == "noisereduction":
                self.changeView(self.noiseReductionMenu)
            elif button == "highsensitivity":
                self.toggleCameraProperty("highSensitivity", buttonHighSensitivity, "\nHigh Sensitivity\nOn\n", "\nHigh Sensitivity\nOff\n", Command.HighSensitivityOn, Command.HighSensitivityOff)
            elif button == "infodisp":
                self.toggleCameraProperty("infoDisplay", buttonInfoDisplay, "\nInfo Display\nOn\n", "\nInfo Display\nOff\n", Command.InfoDisplayOn, Command.InfoDisplayOff, default=False)

        self.toggleCameraProperty("backlightComp", buttonBacklight, "\nBacklight\nComp On\n", "\nBacklight\nComp Off\n", toggle=False)
        self.toggleCameraProperty("highResolution", buttonHighRes, "\nHigh Resolution\nOn\n", "\nHigh Resolution\nOff\n", toggle=False)
        self.toggleCameraProperty("highSensitivity", buttonHighSensitivity, "\nHigh Sensitivity\nOn\n", "\nHigh Sensitivity\nOff\n", toggle=False)
        self.toggleCameraProperty("infoDisplay", buttonInfoDisplay, "\nInfo Display\nOn\n", "\nInfo Display\nOff\n", toggle=False, default=False)

        self.layout().addWidget(frame)
        frame.setFixedSize(700, 400)
        frame.move(self.width() / 2 - frame.width() / 2, self.height() / 2 - frame.height() / 2)
        self.tempUI.append(frame)

    def exposureMenu(self):
        cancelFrame = QFrame()
        cancelFrame.resize(self.size())
        cancelFrame.mousePressEvent = lambda e: self.changeView()
        self.layout().addWidget(cancelFrame)
        self.tempUI.append(cancelFrame)

        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setFrameShadow(QFrame.Raised)
        frame.setLineWidth(5)
        frame.setAutoFillBackground(True)
        layout = QVBoxLayout()
        buttonFrame = QFrame()
        buttonLayout = QHBoxLayout()
        buttonFrame.setLayout(buttonLayout)
        buttonFrame.setFont(QFont("MS Shell Dlg 2", 14))
        frame.setLayout(layout)
        title = QLabel("Exposure Mode")
        title.setFont(QFont("MS Shell Dlg 2", 20))
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(buttonFrame)

        def buttonCallback(button):
            if button=="auto":
                self.doCameraCommand(Command.ExposureAuto)
            elif button=="shutter":
                self.doCameraCommand(Command.ExposureShutterPriority)
            elif button=="iris":
                self.doCameraCommand(Command.ExposureIrisPriority)
            elif button=="manual":
                self.doCameraCommand(Command.ExposureManual)

            time.sleep(0.05) # urghh
            self.updateCameraProperties(type="block", full=False)
            highlightButton(self.selectedCamera.properties.exposureMode, buttons)
            # self.changeView() # close the popup

        buttonAuto = QPushButton("\nFull Auto\n\n")
        buttonAuto.clicked.connect(lambda event: buttonCallback("auto"))
        buttonPriority = QPushButton("\nShutter Priority\n\n")
        buttonPriority.clicked.connect(lambda event: buttonCallback("shutter"))
        buttonIris = QPushButton("\nIris Priority\n\n")
        buttonIris.clicked.connect(lambda event: buttonCallback("iris"))
        buttonManual = QPushButton("\nManual\n\n")
        buttonManual.clicked.connect(lambda event: buttonCallback("manual"))
        buttonLayout.addWidget(buttonAuto)
        buttonLayout.addWidget(buttonPriority)
        buttonLayout.addWidget(buttonIris)
        buttonLayout.addWidget(buttonManual)

        buttons = [buttonAuto,None,None,buttonManual,None,None,None,None,None,None,buttonPriority,buttonIris]
        # weird things because the mode is also weird, also datasheet is wrong
        styleButtons(buttons)
        highlightButton(self.selectedCamera.properties.exposureMode, buttons)

        self.layout().addWidget(frame)
        frame.setFixedSize(500,200)
        frame.move(self.width()/2-frame.width()/2,self.height()/2-frame.height()/2)
        self.tempUI.append(frame)

    def whitebalanceMenu(self):
        cancelFrame = QFrame()
        cancelFrame.resize(self.size())
        cancelFrame.mousePressEvent = lambda e: self.changeView()
        self.layout().addWidget(cancelFrame)
        self.tempUI.append(cancelFrame)

        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setFrameShadow(QFrame.Raised)
        frame.setLineWidth(5)
        frame.setAutoFillBackground(True)
        layout = QVBoxLayout()
        buttonFrame = QFrame()
        buttonLayout = QHBoxLayout()
        buttonFrame.setLayout(buttonLayout)
        buttonFrame.setFont(QFont("MS Shell Dlg 2", 14))
        frame.setLayout(layout)
        title = QLabel("White Balance")
        title.setFont(QFont("MS Shell Dlg 2", 20))
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(buttonFrame)

        def buttonCallback(button):
            if button == "auto":
                self.doCameraCommand(Command.WBAuto)
            elif button == "autotrack":
                self.doCameraCommand(Command.WBATW)
            elif button == "indoor":
                self.doCameraCommand(Command.WBIndoor)
            elif button == "outdoor":
                self.doCameraCommand(Command.WBOutdoor)
            elif button == "onepush":
                self.doCameraCommand(Command.WBOnePush)
            elif button == "manual":
                self.doCameraCommand(Command.WBManual)

            self.updateCameraProperties()
            highlightButton(self.selectedCamera.properties.whiteBalanceMode, buttons)
            # self.changeView()  # close the popup

        buttonAuto = QPushButton("\nAuto WB\n\n")
        buttonAuto.clicked.connect(lambda event: buttonCallback("auto"))
        buttonAutoTrack = QPushButton("\nAuto\nTracking\n")
        buttonAutoTrack.clicked.connect(lambda event: buttonCallback("autotrack"))
        buttonIndoor = QPushButton("\nIndoor\n\n")
        buttonIndoor.clicked.connect(lambda event: buttonCallback("indoor"))
        buttonOutdoor = QPushButton("\nOutdoor\n\n")
        buttonOutdoor.clicked.connect(lambda event: buttonCallback("outdoor"))
        buttonOnePush = QPushButton("\nOne Push\n\n")
        buttonOnePush.clicked.connect(lambda event: buttonCallback("onepush"))
        buttonManual = QPushButton("\nManual\n\n")
        buttonManual.clicked.connect(lambda event: buttonCallback("manual"))
        buttonLayout.addWidget(buttonAuto)
        buttonLayout.addWidget(buttonAutoTrack)
        buttonLayout.addWidget(buttonIndoor)
        buttonLayout.addWidget(buttonOutdoor)
        buttonLayout.addWidget(buttonOnePush)
        buttonLayout.addWidget(buttonManual)

        buttons = [buttonAuto, buttonIndoor, buttonOutdoor, buttonOnePush, buttonAutoTrack, buttonManual]
        styleButtons(buttons)
        highlightButton(self.selectedCamera.properties.whiteBalanceMode, buttons)

        self.layout().addWidget(frame)
        frame.setFixedSize(600, 200)
        frame.move(self.width() / 2 - frame.width() / 2, self.height() / 2 - frame.height() / 2)
        self.tempUI.append(frame)

    def dynamicRangeMenu(self):
        cancelFrame = QFrame()
        cancelFrame.resize(self.size())
        cancelFrame.mousePressEvent = lambda e: self.changeView()
        self.layout().addWidget(cancelFrame)
        self.tempUI.append(cancelFrame)

        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setFrameShadow(QFrame.Raised)
        frame.setLineWidth(5)
        frame.setAutoFillBackground(True)
        layout = QVBoxLayout()
        buttonFrame = QFrame()
        buttonLayout = QHBoxLayout()
        buttonFrame.setLayout(buttonLayout)
        buttonFrame.setFont(QFont("MS Shell Dlg 2", 14))
        frame.setLayout(layout)
        title = QLabel("Wide Dynamic Range [No FBQ :(]")
        title.setFont(QFont("MS Shell Dlg 2", 20))
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(buttonFrame)

        def buttonCallback(button):
            if button == "off":
                self.doCameraCommand(Command.WideDynamicRangeOff)
            elif button == "low":
                self.doCameraCommand(Command.WideDynamicRangeLow)
            elif button == "medium":
                self.doCameraCommand(Command.WideDynamicRangeMed)
            elif button == "high":
                self.doCameraCommand(Command.WideDynamicRangeHigh)
            # self.changeView()  # close the popup

        buttonOff = QPushButton("\nOff\n\n")
        buttonOff.clicked.connect(lambda event: buttonCallback("off"))
        buttonLow = QPushButton("\nLow\n\n")
        buttonLow.clicked.connect(lambda event: buttonCallback("low"))
        buttonMedium = QPushButton("\nMedium\n\n")
        buttonMedium.clicked.connect(lambda event: buttonCallback("medium"))
        buttonHigh = QPushButton("\nHigh\n\n")
        buttonHigh.clicked.connect(lambda event: buttonCallback("High"))
        buttonLayout.addWidget(buttonOff)
        buttonLayout.addWidget(buttonLow)
        buttonLayout.addWidget(buttonMedium)
        buttonLayout.addWidget(buttonHigh)

        buttons = [buttonOff, buttonLow, buttonMedium, buttonHigh]
        styleButtons(buttons)
        # can't highlight button until add more inquiries

        self.layout().addWidget(frame)
        frame.setFixedSize(600, 200)
        frame.move(self.width() / 2 - frame.width() / 2, self.height() / 2 - frame.height() / 2)
        self.tempUI.append(frame)

    def noiseReductionMenu(self):
        cancelFrame = QFrame()
        cancelFrame.resize(self.size())
        cancelFrame.mousePressEvent = lambda e: self.changeView()
        self.layout().addWidget(cancelFrame)
        self.tempUI.append(cancelFrame)

        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setFrameShadow(QFrame.Raised)
        frame.setLineWidth(5)
        frame.setAutoFillBackground(True)
        layout = QVBoxLayout()
        buttonFrame = QFrame()
        buttonLayout = QHBoxLayout()
        buttonFrame.setLayout(buttonLayout)
        frame.setLayout(layout)
        title = QLabel("Noise Reduction Level")
        title.setFont(QFont("MS Shell Dlg 2", 20))
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(buttonFrame)

        def buttonCallback(button):
            if button == "off":
                self.doCameraCommand(Command.NoiseReductionOff)
            elif button == "1":
                self.doCameraCommand(Command.NoiseReduction(1))
            elif button == "2":
                self.doCameraCommand(Command.NoiseReduction(2))
            elif button == "3":
                self.doCameraCommand(Command.NoiseReduction(3))
            elif button == "4":
                self.doCameraCommand(Command.NoiseReduction(4))
            elif button == "5":
                self.doCameraCommand(Command.NoiseReduction(5))
            self.updateCameraProperties()
            highlightButton(self.selectedCamera.properties.noiseReduction, buttons)
            # self.changeView()  # close the popup

        buttonOff = QPushButton("\nOff\n\n")
        buttonOff.clicked.connect(lambda event: buttonCallback("off"))
        button1 = QPushButton("\n1\n\n")
        button1.clicked.connect(lambda event: buttonCallback("1"))
        button2 = QPushButton("\n2\n\n")
        button2.clicked.connect(lambda event: buttonCallback("2"))
        button3 = QPushButton("\n3\n\n")
        button3.clicked.connect(lambda event: buttonCallback("3"))
        button4 = QPushButton("\n4\n\n")
        button4.clicked.connect(lambda event: buttonCallback("4"))
        button5 = QPushButton("\n5\n\n")
        button5.clicked.connect(lambda event: buttonCallback("5"))
        buttonLayout.addWidget(buttonOff)
        buttonLayout.addWidget(button1)
        buttonLayout.addWidget(button2)
        buttonLayout.addWidget(button3)
        buttonLayout.addWidget(button4)
        buttonLayout.addWidget(button5)

        buttons = [buttonOff,button1,button2,button3,button4,button5]
        styleButtons(buttons)
        highlightButton(self.selectedCamera.properties.noiseReduction, buttons)

        self.layout().addWidget(frame)
        frame.setFixedSize(500, 200)
        frame.move(self.width() / 2 - frame.width() / 2, self.height() / 2 - frame.height() / 2)
        self.tempUI.append(frame)

    def shutdownScreen(self):
        self.labelTopLeft.setText("Discover Cameras")
        self.labelMidLeft.setText("Home Screen")
        self.labelBottomLeft.setText("Settings")
        self.labelCenterLeft.setText("Recall Preset")
        self.labelCenterMid.setText("Store Preset")
        self.labelCenterRight.setText("Exit to Desktop")
        self.labelBottomRight.setText("Restart PiControl")
        self.labelMidRight.setText("Restart pi")
        self.labelTopRight.setText("Shutdown pi")
        self.labelCurrentScreen.setText("Shutdown / Reboot Menu")
        self.textView.hide()

        def shutdown():
            if os.name != "posix":
                self.popup("Unable to shutdown")
                return
            os.system("shutdown now")
        def reboot():
            if os.name != "posix":
                self.popup("Unable to reboot")
                return
            os.system("reboot")
        def restartControl():
            self.close()
        def exitThis():
            if os.name == "posix":
                os.system("touch /tmp/norestart")
            self.close()

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.changeView(self.homeScreen),
            "MidLeft": lambda: self.changeView(self.cameraConfigScreen),
            "BottomLeft": lambda: self.changeView(self.networkConfigScreen),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
            "TopRight": lambda: shutdown(),
            "MidRight": lambda: reboot(),
            "BottomRight": lambda: restartControl(),
            "CenterRight": lambda: exitThis()
        })

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        log.info("Closing serial threads...")
        self.serial.stop()
        log.info("Stopping camera pinger")
        self.pinger.stop()
        log.info("Stopping cameras")
        for camName, cam in self.cameras.items():
            if cam:
                cam.close()
        log.info("Exiting")
        a0.accept()

if __name__ == '__main__':
    app = QApplication([])
    app.setStyle("Fusion")
    mainUI = MainScreen()
    sys.exit(app.exec())