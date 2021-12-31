import logging
import os
import subprocess

from PyQt5 import QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal

log = logging.getLogger("CameraPinger")
log.setLevel(logging.INFO)


class CameraPinger(QThread):
    cameraUpdate = pyqtSignal(tuple) # (name, status)
    cameras = {}
    cameraList = []
    index = 0
    _isRunning=True

    def __init__(self, ticker=None, cameras=None):
        QThread.__init__(self)
        self.setTerminationEnabled(True)
        self.ticker = ticker # UI element to see if it's still working
        self.setCameras(cameras)
    def __del__(self):
        pass

    def setCameras(self,cameras):
        self.cameras = cameras # hopefully this is a reference
        self.cameraList = list(cameras)
        self.index = 0

    def stop(self):
        self._isRunning=False
        self.quit()
        self.wait()
        self.deleteLater()

    def run(self):
        log.info("Camera pinger Thread started")
        while self._isRunning:
            if len(self.cameraList)>0:
                try:
                    #todo do the ping / camera check
                    cameraName = self.cameraList[self.index]
                    camera = self.cameras[cameraName]
                    ip = camera.ip

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
                        self.cameraList = list(self.cameras) # regenerate list
                    if self.ticker:
                        self.ticker.setText(str(self.index))
                except KeyError:
                    self.index = 0
                    self.cameraList = list(self.cameras)  # regenerate list
            else:
                self.cameraList = list(self.cameras)  # regenerate list
            QtWidgets.qApp.processEvents()

            QThread.msleep(500)