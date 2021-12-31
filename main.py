import os
import socket
import subprocess
import sys
import re
import logging

from getmac import get_mac_address

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QGraphicsScene, QGraphicsRectItem, QListWidgetItem, QMainWindow
from PyQt5.uic import loadUi

import database
from ButtonControl import ButtonControl
from CameraPinger import CameraPinger
from sony_visca.visca_ip_camera import ViscaIPCamera
from sony_visca.visca_commands import Command
from SerialControl import SerialControl


logging.basicConfig(level=logging.INFO)
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

        self.pinger = CameraPinger(self.ticker, self.cameras)
        self.pinger.cameraUpdate.connect(self.pingCameraCallback)
        self.pinger.start()

        self.show()

        self.discoverCameras()
        self.debug()
        self.nextCamera() # select a camera to start with please

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        super(MainScreen, self).keyPressEvent(event)
        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            log.debug("Keyboard Escape pressed")
            self.ButtonControl.escape()
        elif key == QtCore.Qt.Key_Return:
            log.debug("Keyboard Enter pressed")
            self.ButtonControl.ButtonEnter()

    def debug(self):
        temp = ViscaIPCamera("LaurieC3","192.168.0.68","DC:ED:84:A1:9A:77",simple_visca=True, port=1259)
        temp.initialise()
        self.cameras["LaurieC3 [192.168.0.68]"] = temp
        self.cameraListWidget.addItem(QListWidgetItem("LaurieC3 [192.168.0.68]"))
        self.cameras["LaurieC3 [TEST]"] = temp
        self.cameraListWidget.addItem(QListWidgetItem("LaurieC3 [TEST]"))
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
            log.log(0,"Ping camera callback:",camera,"status",status)
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
            self.selectedCamera.queueCommands(command, override=False)
        else:
            self.selectedCamera.queueCommands(Command(command, **kwargs), override=False)

    def getManualCamerasFromdb(self):
        """Get camera objects from DB data"""
        rows = database.query("SELECT * FROM cameras WHERE autocreated = 0")
        extras = []
        for row in rows:
            if row["type"] == "sony":
                extras.append(ViscaIPCamera(row["name"], row["ip"], None))
            else:
                extras.append(ViscaIPCamera(row["name"], row["ip"], None, port=1259, simple_visca=True))
        log.info("Found %d extra cameras (from db)", len(extras))
        return extras

    def discoverCameras(self):
        #todo close socket connections (and stop any cameras moving)
        #todo move this crap to a thread
        self.infoPopup.setText("Searching...")
        self.infoPopup.show()
        updateUI()
        log.info("Searching for cameras")
        found = ViscaIPCamera.discoverCameras()
        log.info("Found %d cameras", len(found))
        updateUI()
        self.infoPopup.setText("Found "+str(len(found))+" cameras") #todo make this popup appear for a second or something
        updateUI()
        QTimer.singleShot(500, self.infoPopup.hide)

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

        known_ips = [c.ip for c in self.cameras.items()] # old list of ips
        self.cameras.clear()  # do NOT re-initialise as we've passed a reference to other bits

        if found:
            for cam in found:
                if cam.ip not in known_ips:
                    try:
                        cam.initialise()
                    except socket.timeout:
                        # probably camera is on a different network
                        log.warning("Failed to initialise camera %s",str(cam))
                log.info("Adding '%s'",str(cam))
                self.cameras[str(cam)] = cam
                self.cameraListWidget.addItem(QListWidgetItem(str(cam)))


    def changeSelectedCamera(self):
        if self.selectedCamera and self.selectedCamera.is_connected:
            # todo: send all these on a different thread: or with new library and queueing it might be ok
            self.selectedCamera.queueCommands(Command(Command.PanTiltStop()), Command(Command.ZoomStop), Command(Command.FocusStop), override=True)

        cameraName = self.cameraListWidget.currentItem().text()
        log.info("Selected camera changed to %s",cameraName)
        self.labelInfo.setText(cameraName)
        try:
            self.selectedCamera = self.cameras[cameraName]
            self.selectedCameraName = cameraName
        except KeyError:
            log.warning("Tried to switch camera to a non-existent camera; has it been deleted?")

        #todo update positions frame stuff

    def nextCamera(self, increment=1):
        # increment allows for going backwards (-1) and other funky things
        log.info("Next camera")
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
        self.labelBottomLeft.setText("Settings")
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
            #todo get old ip
            def setSubnet(newSubnet):
                if newSubnet==None:
                    self.popup("Canceled",500)
                    return
                #todo: validate?
                #todo set the IP and subnet
                log.info("Changing camera IP/sub",self.selectedCameraName,"to",self._tempIPAddress,"/",newSubnet)
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
            if self.selectedCamera:
                def setName(newName):
                    if newName==None or newName=="":
                        self.popup("Canceled",500)
                        return
                    # todo set name
                    log.info("Changing camera name", self.selectedCamera.name, "to",newName)
                self.ButtonControl.input(self.selectedCamera.name,"Camera Name",setName)
            else:
                self.popup("No camera selected!")

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
        self.labelBottomRight.setText("Set Ras-Pi IP")
        self.labelMidRight.setText("")
        self.labelTopRight.setText("Add Manual Camera")
        self.labelCurrentScreen.setText("Settings")

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
                            cam = ViscaIPCamera(newName, ip, mac)
                            self.cameras[str(cam)] = cam
                            self.cameraListWidget.addItem(QListWidgetItem(str(cam)))
                            log.debug("Adding new camera[%s,%s,%s] to database", newName, newip_,mac)
                            database.query(
                                "INSERT INTO cameras (name, ip, type, mac, autocreated) VALUES (?, ?, ?, ?, 0)",
                                (newName, newip_, "chinese", mac),
                            )

                    except socket.error:
                        self.popup("Invalid IP Address!")
                        return

                self.ButtonControl.input("", "Camera IP", setIP)

            self.ButtonControl.input("", "Camera Name", setName)

        self.ButtonControl.connectFunctions({
            "TopLeft": lambda: self.discoverCameras(),
            "MidLeft": lambda: self.cameraConfigScreen(),
            "BottomLeft": lambda: self.homeScreen(),
            "BottomRight": lambda: changeIP(),
            "TopRight": lambda: addCamera(),
            "CenterLeft": lambda: self.recallPreset(),
            "CenterMid": lambda: self.storePreset(),
            "Next": lambda: self.nextCamera(),
            "Prev": lambda: self.nextCamera(-1),
        })

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        log.info("Closing serial threads...")
        self.serial.stop()
        log.info("Stopping camera pinger")
        self.pinger.stop()
        log.info("Stopping cameras")
        for camName, cam in self.cameras.items():
            cam.close()
        log.info("Exiting")
        a0.accept()

if __name__ == '__main__':
    app = QApplication([])
    app.setStyle("Fusion")
    mainUI = MainScreen()
    sys.exit(app.exec())