from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QLabel, QGridLayout, QWidget, QPushButton, QGraphicsScene, QGraphicsRectItem, QListWidgetItem
from PyQt5.uic import loadUi

app = QApplication([])

class MainScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.selectedCamera = None
        self.cameras = {}

        loadUi("MainUI.ui", self)

        self.setWindowTitle("PTZ Controller")
        camPosScene = QGraphicsScene(self)
        self.graphicsView.setScene(camPosScene)
        self.camPosRect = QGraphicsRectItem(QtCore.QRectF(0, 0, 5, 5))
        self.camPosRect.setBrush(QColor(255, 0, 0))
        self.camPosRect.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        camPosScene.addItem(self.camPosRect)

        self.cameraListWidget.currentItemChanged.connect(self.changeSelectedCamera)

        self.discoverCameras()
        self.homeScreen()

        self.show()

    def drawCameraPos(self):
        self.camPosRect #todo: do something with this
        pass

    def discoverCameras(self):
        self.cameras = {} # todo: remember lost cameras?
        # todo actually discover cameras (names should be unique enough with IPs)
        self.cameras = {"CAM1 (10.0.1.20) [SONY]": None,
                        "CAM2 - LAURIE (10.0.1.999) [CHINESE]": None,
                        "CAM3 WOWEE (10.0.1.342)": None,
                        "CAM4 TROTT (10.0.1.65)": None}
        for camName in self.cameras:
            self.cameraListWidget.addItem(QListWidgetItem(camName))
        self.cameraListWidget.item(1).setForeground(QColor(255,0,0))

    def changeSelectedCamera(self):
        cameraName = self.cameraListWidget.currentItem().text()
        print("Selected camera",cameraName)
        self.labelInfo.setText(cameraName)
        self.selectedCamera = self.cameras[cameraName]

        #todo update positions frame stuff
        #todo stop camera moving in any way if we were controlling it before switching

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


if __name__ == '__main__':
    app.setStyle("Fusion")
    mainUI = MainScreen()
    app.exec()