import logging
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("PiControl")

def doTrimBecauseJamieSucks(r):
    return r[8:]


class CameraProperties:
    def __init__(self):
        self.destinationAddress = 0
        self.sourceAddress = 0
        self.completion = False
        self.RGain = 0
        self.BGain = 0
        self.whiteBalanceMode = 0
        self.whiteBalanceSpeed = 0
        self.apertureGain = 0
        self.exposureMode = 0
        self.colorMatrix = 0
        self.autoSlowShutter = False
        self.exposureCompOn = False
        self.backlightComp = False
        self.visibilityEnhancer = False
        self.highSensitivity = False
        self.shutter = 0
        self.iris = 0
        self.gain = 0
        self.exposureComp = 0
        self.zoom = 0
        self.gamma = 0
        self.focusNearLimit = 0
        self.focus = 0
        self.autoFocus = 0
        self.digitalZoom = False
        self.digitalZoomPos = 0
        self.zoomMode = False
        self.autoFocusMode = 0
        self.autoFocusSensitivity = 0
        self.autoFocusActivationTime = 0
        self.autoFocusIntervalTime = 0
        self.lowContrastDetection = False
        self.memoryRecall = False
        self.focusCommand = False
        self.zoomCommand = False
        self.highResolution = False
        self.wideDynamicRange = False
        self.noiseReduction = 0
        self.gainLimit = 0
        self.chromaSuppress = 0
        self.colorHue = 0
        self.power = True
        self.defog = False
        self.pictureEffect = 0
        self.colorGain = 0
        self.cameraID = 0
        self.dropFrame = True

    def decodeBlockLens(self, response):
        if response is None:
            log.warning("Block Lens Inquiry responded with None")
            return

        if len(response)<15:
            log.warning("Block Lens Inquiry repsonse was too short")
            return

        response = doTrimBecauseJamieSucks(response)
        self.destinationAddress = (response[0] & 0xf0) >> 4
        self.sourceAddress = response[0] & 0x0f
        self.completion = bool(response[1]&0x80)
        self.zoom = ((response[2]&0x0f)<<12) | ((response[3]&0x0f)<<8) | ((response[4]&0x0f)<<4) | (response[5]&0x0f)
        self.focusNearLimit = ((response[6]&0x0f)<<4) | (response[7]&0x0f)
        self.focus = ((response[8]&0x0f)<<12) | ((response[9]&0x0f)<<8) | ((response[10]&0x0f)<<4) | (response[11]&0x0f)
        self.autoFocus = bool(response[13]&0x01)
        self.digitalZoom = bool(response[13]&0x02)
        self.autoFocusSensitivity = bool(response[13]&0x04)
        self.autoFocusMode = (response[13] & 0x18) >> 3
        self.lowContrastDetection = bool(response[14]&0x08)
        self.memoryRecall = bool(response[14]&0x04) # is executing a command
        self.focusCommand = bool(response[14]&0x02)
        self.zoomCommand = bool(response[14]&0x01)

    def decodeBlockControl(self,response):
        if response is None:
            log.warning("Block Control Inquiry responded with None")
            return
        if len(response)<14:
            log.warning("Block Control Inquiry repsonse was too short")
            return

        response = doTrimBecauseJamieSucks(response)
        self.destinationAddress=(response[0] & 0xf0) >> 4
        self.sourceAddress = response[0] & 0x0f
        self.completion = bool(response[1] & 0x80)
        self.RGain = ((response[2] & 0x0f) << 4) | (response[3] & 0x0f)
        self.BGain = ((response[4] & 0x0f) << 4) | (response[5] & 0x0f)
        self.whiteBalanceMode = response[6] & 0x0f
        self.apertureGain = response[7] & 0x0f
        self.exposureMode = response[8] & 0x0f
        self.highResolution = bool(response[9]&0x20)
        self.wideDynamicRange = bool(response[9]&0x10)
        self.autoSlowShutter = bool(response[9] & 0x01)
        self.exposureCompOn = bool(response[9] & 0x02)
        self.backlightComp = bool(response[9] & 0x04)
        self.shutter = response[10] & 0x3f
        self.iris = response[11] & 0x1f
        self.gain = response[12] & 0x1f
        self.exposureComp = response[13] & 0x0f

    def decodeBlockOther(self, response):
        if response is None:
            log.warning("Block Other Inquiry responded with None")
            return
        if len(response)<13:
            log.warning("Block Other Inquiry repsonse was too short")
            return

        response = doTrimBecauseJamieSucks(response)
        self.destinationAddress = (response[0] & 0xf0) >> 4
        self.sourceAddress = response[0] & 0x0f
        self.completion = bool(response[1] & 0x80)
        self.power = bool(response[2]&0x01)
        self.pictureEffect = response[5]&0x0f
        self.cameraID = ((response[8]&0x0f)<<12) | ((response[9]&0x0f)<<8) | ((response[10]&0x0f)<<4) | (response[11]&0x0f)
        self.dropFrame = bool(response[12]&0x01)

    def decodeBlockEnlargement1(self, response):
        if response is None:
            log.warning("Block Enlargment1 Inquiry responded with None")
            return
        if len(response)<15:
            log.warning("Block Enlargment1 Inquiry repsonse was too short")
            return

        response = doTrimBecauseJamieSucks(response)
        self.destinationAddress = (response[0] & 0xf0) >> 4
        self.sourceAddress = response[0] & 0x0f
        self.completion = bool(response[1] & 0x80)
        self.digitalZoomPos = ((response[2]&0x0f)<<4) | (response[3]&0x0f)
        self.autoFocusActivationTime = ((response[4]&0x0f)<<4) | (response[5]&0x0f)
        self.autoFocusIntervalTime = ((response[6]&0x0f)<<4) | (response[7]&0x0f)
        self.colorGain = (response[11]&0x78) >> 3
        self.gamma = (response[13]&70) >> 4
        self.highSensitivity = bool(response[13]&0x08)
        self.noiseReduction = response[13]&0x07
        self.gainLimit = response[14]&0x0f
        self.chromaSuppress = (response[14]&0x70)>>4

    def decodeBlockEnlargement2(self, response):
        if response is None:
            log.warning("Block Enlargement2 Inquiry responded with None")
            return
        if len(response)<8:
            log.warning("Block Enlargement2 Inquiry repsonse was too short")
            return

        response = doTrimBecauseJamieSucks(response)
        self.destinationAddress = (response[0] & 0xf0) >> 4
        self.sourceAddress = response[0] & 0x0f
        self.completion = bool(response[1] & 0x80)
        self.defog = bool(response[7]&0x01)

    def decodeBlockEnlargement3(self, response):
        if response is None:
            log.warning("Block Enlargement3 Inquiry responded with None")
            return
        if len(response)<3:
            log.warning("Block Enlargement3 Inquiry repsonse was too short")
            return

        response = doTrimBecauseJamieSucks(response)
        self.destinationAddress = (response[0] & 0xf0) >> 4
        self.sourceAddress = response[0] & 0x0f
        self.completion = bool(response[1] & 0x80)
        self.colorHue = response[2]&0x07


