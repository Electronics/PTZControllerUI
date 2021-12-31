import serial
import logging
import re
import traceback
from PyQt5.QtCore import QThread, pyqtSignal
from sony_visca.visca_commands import Command

log = logging.getLogger("SerialControl")
log.setLevel(logging.DEBUG)

SERIAL_PORT = "COM8"
JOYSTICK_NUM_STEPS = 16 # number of steps in the +ve and -ve directions

serialRegex = re.compile(r"(?P<command>[A-Z]+)(?P<num0>-?[0-9]+)?(,(?P<num1>-?[0-9]+)(,(?P<num2>-?[0-9]+),(?P<num3>-?[0-9]+),(?P<num4>-?[0-9]+),(?P<num5>-?[0-9]+)(,(?P<num6>-?[0-9]+),(?P<num7>-?[0-9]+),(?P<num8>-?[0-9]+))?)?)?")

class SerialControl(QThread):
    buttonPressSignal = pyqtSignal(int)
    buttonReleaseSignal = pyqtSignal(int)
    uiSignal = pyqtSignal(list)
    cameraControl = pyqtSignal(object)

    _isRunning = True

    port = None
    learning = False

    # velocities (to keep track of where the joystick is, i.e. diagonal)
    # maybe I should have tracked this on the uC side
    vx = 0
    vy = 0
    vz = 0
    vx_last = 0
    vy_last = 0
    vz_last = 0

    def initPort(self):
        try:
            self.port = serial.Serial(SERIAL_PORT, 115200)

            self.port.write(b'HELLO\n')
        except serial.SerialException:
            log.error("Failed to open serial port")
    def __init__(self):
        QThread.__init__(self)
        self.initPort()
    def __del__(self):
        if self.isConnected():
            self.port.close()

    def moveCam(self):
        if self.vx_last != self.vx or self.vy_last != self.vy:
            self.vx_last = self.vx
            self.vy_last = self.vy
            cmd = None
            if self.vx == 0 and self.vy == 0:
                # Stop
                cmd = Command.PanTiltStop()
                log.debug("move stop")
            elif self.vx < 0 and self.vy == 0:
                # Left
                cmd = Command.PanTiltLeft(panSpeed=self.vx * -1)
                log.debug("moving left")
            elif self.vx > 0 and self.vy == 0:
                # Right
                cmd = Command.PanTiltRight(panSpeed=self.vx)
                log.debug("moving right")
            elif self.vx == 0 and self.vy > 0:
                # Up
                cmd = Command.PanTiltUp(tiltSpeed=self.vy)
                log.debug("moving up")
            elif self.vx == 0 and self.vy < 0:
                # Down
                cmd = Command.PanTiltDown(tiltSpeed=self.vy * -1)
                log.debug("moving down")
            elif self.vx < 0 and self.vy > 0:
                # Up Left
                cmd = Command.PanTiltUpLeft(panSpeed=self.vx * -1, tiltSpeed=self.vy)
                log.debug("moving up-left")
            elif self.vx > 0 and self.vy > 0:
                # Up Right
                cmd = Command.PanTiltUpRight(panSpeed=self.vx, tiltSpeed=self.vy)
                log.debug("moving up-right")
            elif self.vx < 0 and self.vy < 0:
                # Down Left
                cmd = Command.PanTiltDownLeft(panSpeed=self.vx * -1, tiltSpeed=self.vy * -1)
                log.debug("moving down-left")
            elif self.vx > 0 and self.vy < 0:
                # Down Right
                cmd = Command.PanTiltDownRight(panSpeed=self.vx, tiltSpeed=self.vy * -1)
                log.debug("moving down-right")
            if cmd:
                self.cameraControl.emit(Command(cmd))

        if self.vz_last != self.vz:
            self.vz_last = self.vz
            if self.vz == 0:
                log.debug("zoom stop")
                cmd = Command.ZoomStop
            elif self.vz > 0:
                log.debug("zoom in")
                cmd = Command.ZoomTeleVariable(abs(self.vz))
            else:
                log.debug("zoom out")
                cmd = Command.ZoomWideVariable(abs(self.vz))
            if cmd:
                self.cameraControl.emit(Command(cmd))

    def isConnected(self):
        if not self.port or not self.port.is_open:
            return False
        return True

    def stop(self):
        self._isRunning=False
        if self.isConnected():
            self.port.close()
        self.quit()
        self.wait()
        self.deleteLater()

    def run(self):
        print("Serial Thread started")
        if not self.isConnected():
            log.warning("Serial port not found, aborting external control")
            self._isRunning = False
            return
        while self._isRunning:
            try:
                while True:
                    data = self.port.readline().decode("utf-8").strip()
                    dataSplit = serialRegex.search(data)
                    log.debug("Serial data: %s",data)
                    if not dataSplit:
                        log.warning("No data in serial command")
                        continue
                    command = dataSplit["command"]
                    try:
                        movementCommand = False
                        # pan 1-slow to 18-fast, tilt 1-slow to 17-fast
                        if command=="X":
                            x = int(dataSplit["num0"])
                            self.vx = int(float(x)/JOYSTICK_NUM_STEPS*18)
                            log.debug("X position %d converted to speed %d", x, self.vx)
                            movementCommand = True
                        elif command=="Y":
                            y = int(dataSplit["num0"])
                            self.vy = int(float(y) / JOYSTICK_NUM_STEPS * 17)
                            log.debug("Y position %d converted to speed %d", y, self.vy)
                            movementCommand = True
                        elif command=="Z":
                            z = int(dataSplit["num0"])
                            self.vz = int(float(z) / JOYSTICK_NUM_STEPS * 7)
                            log.debug("Z position %d converted to speed %d", z, self.vz)
                            movementCommand = True
                        elif command=="P":
                            button = int(dataSplit["num0"])*8 + int(dataSplit["num1"])
                            log.debug("Button Press %d",button)
                            self.buttonPressSignal.emit(button)
                        elif command=="R":
                            button = int(dataSplit["num0"]) * 8 + int(dataSplit["num1"])
                            log.debug("Button Release %d",button)
                        elif command=="BOOT":
                            restX = int(dataSplit["num0"])
                            restY = int(dataSplit["num1"])
                            restZ = int(dataSplit["num2"])
                            stepX = int(dataSplit["num3"])
                            stepY = int(dataSplit["num4"])
                            stepZ = int(dataSplit["num5"])
                            log.info("uC is Booting %d %d %d %d %d %d",restX,restY,restZ,stepX,stepY,stepZ)
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
                            log.debug("Learning mode %s",data)
                            self.uiSignal.emit(["detailedPopupDetails","setText","X:%d Y:%d Z:%d\nminX:%d minY:%d minZ:%d\nmaxX:%d maxY:%d maxZ:%d"%(rawX,rawY,rawZ,minX,minY,minZ,maxX,maxY,maxZ)])
                            if not self.learning:
                                self.learning = True
                                self.uiSignal.emit(["detailedPopupTitle","setText","Joystick Calibration: Move the joystick to all maximum limits, center to home and then press continue"])
                                self.uiSignal.emit(["detailedPopup","show"])
                        elif command=="HOME":
                            log.debug("Learning home")
                            self.uiSignal.emit(["detailedPopupDetails", "setText", "Learning Home Position..."])
                        elif command=="FIN":
                            restX = int(dataSplit["num0"])
                            restY = int(dataSplit["num1"])
                            restZ = int(dataSplit["num2"])
                            stepX = int(dataSplit["num3"])
                            stepY = int(dataSplit["num4"])
                            stepZ = int(dataSplit["num5"])
                            log.debug("Learning finished %d %d %d %d %d %d",restX,restY,restZ,stepX,stepY,stepZ)
                            self.learning = False
                            self.uiSignal.emit(["detailedPopup","hide"])
                            self.uiSignal.emit(["popup","Cal Done!"])
                        else:
                            print("Unknown serial data: %s",data)

                        if movementCommand:
                            self.moveCam()

                    except IndexError:
                        log.error("Index error in decode")

            except:
                if self._isRunning==False:
                    # catch the case when we're exiting
                    continue
                log.error("Exception in data parsing")
                print(traceback.format_exc())
                self.port.close()
                self.initPort()
