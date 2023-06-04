import threading


def bytesOR(b1,b2):
	if len(b1) != len(b2):
		raise ValueError("Array lengths are different")
	for i, b in enumerate(b2):
		b1[i] |= b
	return b1
def bytesAND(b1,b2):
	if len(b1) != len(b2):
		raise ValueError("Array lengths are different")
	for i, b in enumerate(b2):
		b1[i] &= b
	return b1
def byteSet(by, value, position):
	by[position] = value
	return by


class CommandTimeout(Exception):
	"""Timeout waiting for a response from a command"""


class Command:
	"""Wrapper for PTZ commands"""

	def __init__(self, value, skipCompletion=False):
		self.value = value
		self.skipCompletion = skipCompletion
		self._result = None
		self._result_ready = threading.Event()

	@property
	def kwargs(self):
		return {
			"skipCompletion": self.skipCompletion,
		}

	def wait_result(self, timeout=2):
		ready = self._result_ready.wait(timeout)
		if not ready:
			raise CommandTimeout

	@property
	def result(self):
		"""Get command result"""
		return self._result

	@result.setter
	def result(self, value):
		"""Set command result"""
		self._result = value
		self._result_ready.set()

	def __repr__(self):
		return f"<Command: {self.value!r}>"

	# Commands
	PowerOn = bytearray.fromhex("8101040002ff")
	PowerOff = bytearray.fromhex("8101040003ff")
	ZoomStop = bytearray.fromhex("8101040700ff")
	ZoomTele = bytearray.fromhex("8101040702ff")
	ZoomWide = bytearray.fromhex("8101040703ff")
	@classmethod
	def ZoomTeleVariable(cls, speed):
			return byteSet(cls.ZoomTele, (speed & 7) | 0x20, 4)
	@classmethod
	def ZoomWideVariable(cls, speed):
			return byteSet(cls.ZoomTele, (speed & 7) | 0x30, 4)
	@classmethod
	def ZoomPos(cls, pos):
		# 0-0x4000 analog, 0x4000-0x7AC0 digital
		pos = "%0.4x" % (pos & 0xFFFF)
		return bytearray.fromhex("810104470%s0%s0%s0%sff"%(pos[0],pos[1],pos[2],pos[3]))
	DigitalZoomOn = bytearray.fromhex("8101040602ff")
	DigitalZoomOff = bytearray.fromhex("8101040603ff")
	FocusStop = bytearray.fromhex("8101040800ff")
	FocusFar = bytearray.fromhex("8101040802ff")
	FocusNear = bytearray.fromhex("8101040803ff")
	@classmethod
	def FocusFarVariable(cls, speed):
			return byteSet(cls.FocusFar, (speed & 7) | 0x20, 4)
	@classmethod
	def FocusNearVariable(cls, speed):
			return byteSet(cls.FocusFar, (speed & 7) | 0x30, 4)
	@classmethod
	def FocusPos(cls, pos):
		# 0-0x4000?
		pos = "%0.4x" % (pos & 0xFFFF)
		return bytearray.fromhex("810104480%s0%s0%s0%sff" % (pos[0], pos[1], pos[2], pos[3]))
	AutoFocus = bytearray.fromhex("8101043802ff")
	ManualFocus = bytearray.fromhex("8101043803ff")
	AutoManualFocus = bytearray.fromhex("8101043810ff") # switches?
	FocusOnePush = bytearray.fromhex("8101041801ff")
	FocusInfinity = bytearray.fromhex("8101041802ff")
	@classmethod
	def FocusNearLimit(cls, pos):
		# 0-0x4000?
		pos = "%0.4x" % (pos & 0xFFFF)
		return bytearray.fromhex("810104280%s0%s0%s0%sff" % (pos[0], pos[1], pos[2], pos[3]))
	AutoFocusSensitivityNormal = bytearray.fromhex("8101045802ff")
	AutoFocusSensitivityLow = bytearray.fromhex("8101045803ff")
	AutoFocusModeNormal = bytearray.fromhex("8101045700ff")
	AutoFocusModeInterval = bytearray.fromhex("8101045701ff")
	AutoFocusModeZoomTrigger = bytearray.fromhex("8101045702ff")
	@classmethod
	def AutoFocusModeIntervalTime(cls, time, speed=7):
		speed = "%0.2x" % (speed & 0xFF)
		time = "%0.2x" % (time & 0xFF)
		return bytearray.fromhex("810104270%s0%s0%s0%sff" % (speed[0], speed[1], time[0], time[1]))
	IRCorrectionStandard = bytearray.fromhex("8101041100ff")
	IRCorrectionIRLight = bytearray.fromhex("8101041101ff")
	@classmethod
	def ZoomFocus(cls, zoomPos, focusPos):
		zoomPos = "%0.4x" % (zoomPos & 0xFFFF)
		focusPos = "%0.4x" % (focusPos & 0xFFFF)
		return bytearray.fromhex("810104470%s0%s0%s0%s0%s0%s0%s0%sff" % (zoomPos[0], zoomPos[1], zoomPos[2], zoomPos[3], focusPos[0], focusPos[1], focusPos[2], focusPos[3]))
	WBAuto = bytearray.fromhex("8101043500ff")
	WBIndoor = bytearray.fromhex("8101043501ff")
	WBOutdoor = bytearray.fromhex("8101043502ff")
	WBOnePush = bytearray.fromhex("8101043503ff")
	WBATW = bytearray.fromhex("8101043504ff")
	WBManual = bytearray.fromhex("8101043505ff")
	WBOnePushTrigger = bytearray.fromhex("8101041005ff")
	RGainReset = bytearray.fromhex("8101040300ff") # red gain (Manual WB)
	RGainUp = bytearray.fromhex("8101040302ff")
	RGainDown = bytearray.fromhex("8101040303ff")
	@classmethod
	def RGainDirect(cls, gain):
		gain = "%0.2x" % (gain & 0xFF)
		return bytearray.fromhex("8101044300000%s0%sff" % (gain[0], gain[1]))
	BGainReset = bytearray.fromhex("8101040400ff") # blue gain  (Manual WB)
	BGainUp = bytearray.fromhex("8101040402ff")
	BGainDown = bytearray.fromhex("8101040403ff")
	@classmethod
	def BGainDirect(cls, gain):
		gain = "%0.2x" % (gain & 0xFF)
		return bytearray.fromhex("8101044400000%s0%sff" % (gain[0], gain[1]))
	ExposureAuto = bytearray.fromhex("8101043900ff")
	ExposureManual = bytearray.fromhex("8101043903ff")
	ExposureShutterPriority = bytearray.fromhex("810104390aff")
	ExposureIrisPriority = bytearray.fromhex("810104390bff")
	ExposureBright = bytearray.fromhex("810104390dff")
	SlowShutterAuto = bytearray.fromhex("8101045a02ff")
	SlowShuterManual = bytearray.fromhex("8101045a03ff")
	ShutterReset = bytearray.fromhex("8101040a00ff")
	ShutterUp = bytearray.fromhex("8101040a02ff")
	ShutterDown = bytearray.fromhex("8101040a03ff")
	@classmethod
	def ShutterDirect(cls, pos):
		pos = "%0.2x" % (pos & 0xFF)
		return bytearray.fromhex("8101044a00000%s0%sff" % (pos[0], pos[1]))
	IrisReset = bytearray.fromhex("8101040b00ff")
	IrisUp = bytearray.fromhex("8101040b02ff")
	IrisDown = bytearray.fromhex("8101040b03ff")
	@classmethod
	def IrisDirect(cls, pos):
		pos = "%0.2x" % (pos & 0xFF)
		return bytearray.fromhex("8101044b00000%s0%sff" % (pos[0], pos[1]))
	GainReset = bytearray.fromhex("8101040c00ff")
	GainUp = bytearray.fromhex("8101040c02ff")
	GainDown = bytearray.fromhex("8101040c03ff")
	@classmethod
	def GainDirect(cls, pos):
		pos = "%0.2x" % (pos & 0xFF)
		return bytearray.fromhex("8101044c00000%s0%sff" % (pos[0], pos[1]))
	@classmethod
	def GainAELimit(cls, gain):
			return byteSet(bytearray.fromhex("8101042c00ff"),(gain & 0x0f), 4) # gain 4-F
	BrightUp = bytearray.fromhex("8101040d02ff")
	BrightDown = bytearray.fromhex("8101040d03ff")
	@classmethod
	def BrightDirect(cls, pos):
		pos = "%0.2x" % (pos & 0xFF)
		return bytearray.fromhex("8101044d00000%s0%s" % (pos[0], pos[1]))
	ExposureCompOn = bytearray.fromhex("8101043e02ff")
	ExposureCompOff = bytearray.fromhex("8101043e03ff")
	ExposureCompReset = bytearray.fromhex("8101040e00ff")
	ExposureCompUp = bytearray.fromhex("8101040e02ff")
	ExposureCompDown = bytearray.fromhex("8101040e03ff")
	@classmethod
	def ExposureCompDirect(cls, pos):
		pos = "%0.2x" % (pos & 0xFF)
		return bytearray.fromhex("8101044e00000%s0%sff" % (pos[0], pos[1]))
	BacklightCompOn = bytearray.fromhex("8101043302ff")
	BacklightCompOff = bytearray.fromhex("8101043303ff")
	WideDynamicRangeOff = bytearray.fromhex("81017e040000ff")
	WideDynamicRangeLow = bytearray.fromhex("81017e040001ff")
	WideDynamicRangeMed = bytearray.fromhex("81017e040002ff")
	WideDynamicRangeHigh = bytearray.fromhex("81017e040003ff")
	DefogOn = bytearray.fromhex("810104370200ff")
	DefogOff = bytearray.fromhex("810104370300ff")
	ApertureReset = bytearray.fromhex("8101040200ff")
	ApertureUp = bytearray.fromhex("8101040202ff")
	ApertureDown = bytearray.fromhex("8101040203ff")
	@classmethod
	def ApertureDirect(cls, gain):
		gain = "%0.2x" % (gain & 0xFF)
		return bytearray.fromhex("8101044200000%s0%s" % (gain[0], gain[1]))
	HighResolutionOn = bytearray.fromhex("8101045202ff")
	HighResolutionOff = bytearray.fromhex("8101045203ff")
	NoiseReductionOff = bytearray.fromhex("8101045300ff")
	@classmethod
	def NoiseReduction(cls, level):
		return byteSet(cls.NoiseReductionOff, level & 0x07, 4)
	GammaStandard = bytearray.fromhex("8101045b00ff")
	@classmethod
	def Gamma(cls, level):
		return byteSet(cls.GammaStandard, level & 0x07, 4)
	HighSensitivityOn = bytearray.fromhex("8101045e02ff")
	HighSensitivityOff = bytearray.fromhex("8101045e03ff")
	PictureEffectOff = bytearray.fromhex("8101046300ff")
	PictureEffectNegative = bytearray.fromhex("8101046302ff")
	PictureEffectBW = bytearray.fromhex("8101046304ff")
	@classmethod
	def MemoryReset(cls, preset):
		return byteSet(bytearray.fromhex("8101043f0000ff"), preset & 0xff, 5)
	@classmethod
	def MemorySet(cls, preset):
		return byteSet(bytearray.fromhex("8101043f0100ff"), preset & 0xff, 5)
	@classmethod
	def MemoryRecall(cls, preset):
		return byteSet(bytearray.fromhex("8101043f0200ff"), preset & 0xff, 5)
	@classmethod
	def IDWrite(cls, id):
		id = "%0.4x" % (id & 0xFFFF)
		return bytearray.fromhex("810104220%s0%s0%s0%sff" % (id[0], id[1], id[2], id[3]))
	ChromaSurpress = lambda level: byteSet(bytearray.fromhex("8101045f00ff"),level & 0xff, 4)
	@classmethod
	def ColorGain(cls, spec, gain):
		return bytearray.fromhex("810104490000%0.2x%0.2xff" % (spec & 0x07, gain & 0x0f))
	@classmethod
	def ColorHue(cls, spec, phase):
		return bytearray.fromhex("8101044f0000%0.2x%0.2xff" % (spec & 0x07, phase & 0x0f))
	LowLatencyLow = bytearray.fromhex("81017e015a02ff")
	LowLatencyNormal = bytearray.fromhex("81017e015a03ff")
	MenuOff = bytearray.fromhex("8101060603ff")
	@classmethod
	def VideoFormatChange(cls, format):
		format = "%0.2x" % (format & 0xFF)
		return bytearray.fromhex("81017e011e0%s0%sff" % (format[0], format[1]))
	ColorSystem = lambda a: byteSet(bytearray.fromhex("81017e01030000ff"),a & 0x03, 6)
	IROn = bytearray.fromhex("8101060802ff")
	IROff = bytearray.fromhex("8101060803ff")
	IRToggle = bytearray.fromhex("8101060810ff")
	ReceiveReturnOn = bytearray.fromhex("81017d01030000ff")
	ReceiveReturnOff = bytearray.fromhex("81017d01130000ff")
	InfoDisplayOn = bytearray.fromhex("81017e011802ff")
	InfoDisplayOff = bytearray.fromhex("81017e011803ff")
	@classmethod
	def PanTiltAbs(cls, panPos=0, tiltPos=0, panSpeed=1, tiltSpeed=1):
		pan = "%0.4x"%(panPos&0xFFFF)
		tilt = "%0.4x"%(tiltPos&0xFFFF)
		return bytearray.fromhex("81010602%0.2x%0.2x0%s0%s0%s0%s0%s0%s0%s0%sff"%(
			panSpeed, tiltSpeed, pan[0], pan[1], pan[2], pan[3],
			tilt[0], tilt[1], tilt[2], tilt[3]
		))
	@classmethod
	def PanTiltRel(cls, panPos=0, tiltPos=0, panSpeed=1, tiltSpeed=1):
		pan = "%0.4x"%(panPos&0xFFFF)
		tilt = "%0.4x"%(tiltPos&0xFFFF)
		return bytearray.fromhex("81010603%0.2x%0.2x0%s0%s0%s0%s0%s0%s0%s0%sff"%(
			panSpeed, tiltSpeed, pan[0], pan[1], pan[2], pan[3],
			tilt[0], tilt[1], tilt[2], tilt[3]
		))
	@classmethod
	def PanTiltUp(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0301ff"%(panSpeed, tiltSpeed))
	@classmethod
	def PanTiltDown(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0302ff" % (panSpeed, tiltSpeed))
	@classmethod
	def PanTiltLeft(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0103ff" % (panSpeed, tiltSpeed))
	@classmethod
	def PanTiltRight(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0203ff" % (panSpeed, tiltSpeed))
	@classmethod
	def PanTiltUpLeft(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0101ff" % (panSpeed, tiltSpeed))
	@classmethod
	def PanTiltUpRight(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0201ff" % (panSpeed, tiltSpeed))
	@classmethod
	def PanTiltDownLeft(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0102ff" % (panSpeed, tiltSpeed))
	@classmethod
	def PanTiltDownRight(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0202ff" % (panSpeed, tiltSpeed))
	@classmethod
	def PanTiltStop(cls, panSpeed=1, tiltSpeed=1):
		return bytearray.fromhex("81010601%0.2x%0.2x0303ff" % (panSpeed, tiltSpeed))
	PanTiltHome = bytearray.fromhex("81010604ff")
	PanTiltReset = bytearray.fromhex("81010605ff")
	@classmethod
	def PanTiltLimitSet(cls, pos, panPos=0, tiltPos=0):# pos=1 UpRight, pos=0 DownLeft
		pan = "%0.4x"%(panPos&0xFFFF)
		tilt = "%0.4x"%(tiltPos&0xFFFF)
		return bytearray.fromhex("8101060700%0.2x0%s0%s0%s0%s0%s0%s0%s0%sff"%(
			pos, pan[0], pan[1], pan[2], pan[3],
			tilt[0], tilt[1], tilt[2], tilt[3]
		))
	@classmethod
	def PanTiltLimitClear(cls, pos, panPos=0, tiltPos=0):# pos=1 UpRight, pos=0 DownLeft
		pan = "%0.4x"%(panPos&0xFFFF)
		tilt = "%0.4x"%(tiltPos&0xFFFF)
		return bytearray.fromhex("8101060701%0.2x0%s0%s0%s0%s0%s0%s0%s0%sff"%(
			pos, pan[0], pan[1], pan[2], pan[3],
			tilt[0], tilt[1], tilt[2], tilt[3]
		))

class Inquiry:
	Power = bytearray.fromhex("81090400ff")
	ZoomPos = bytearray.fromhex("81090447ff")
	DZoomMode = bytearray.fromhex("81090447ff")
	FocusMode = bytearray.fromhex("81090438ff")
	FocusPos = bytearray.fromhex("81090448ff")
	FocusNearLimit = bytearray.fromhex("81090428ff")
	AutoFocusSensitivty = bytearray.fromhex("81090458ff")
	AutoFocusMode = bytearray.fromhex("81090457ff")
	AutoFocusInterval = bytearray.fromhex("81090427ff")
	IR = bytearray.fromhex("81090411ff")
	WBMode = bytearray.fromhex("81090435ff")
	RGain = bytearray.fromhex("81090443ff")
	BGain = bytearray.fromhex("81090444ff")
	AEMode = bytearray.fromhex("81090439ff")
	SlowShutterMode = bytearray.fromhex("8109045aff")
	ShutterPos = bytearray.fromhex("8109044aff")
	IrisPos = bytearray.fromhex("8109044bff")
	GainPos = bytearray.fromhex("8109044cff")
	GainLimit = bytearray.fromhex("8109042cff")
	BrightPos = bytearray.fromhex("8109044dff")
	ExposureCompMode = bytearray.fromhex("8109043eff")
	ExposureCompPos = bytearray.fromhex("8109044eff")
	BacklightMode = bytearray.fromhex("81090433ff")
	WDMode = bytearray.fromhex("81097e0400ff")
	Defog = bytearray.fromhex("81090437ff")
	Aperture = bytearray.fromhex("81090442ff")
	HighResolutionMode = bytearray.fromhex("81090452ff")
	NR = bytearray.fromhex("81090453ff")
	Gamma = bytearray.fromhex("8109045bff")
	HighSensitivity = bytearray.fromhex("8109045eff")
	PictureEffectMode = bytearray.fromhex("81090463ff")
	ID = bytearray.fromhex("81090422ff")
	Version = bytearray.fromhex("81090002ff")
	ChromaSuppress = bytearray.fromhex("8109045fff")
	ColorGain = bytearray.fromhex("81090449ff")
	ColorHue = bytearray.fromhex("8109044fff")
	LowLatency = bytearray.fromhex("81097e015aff")
	MenuMode = bytearray.fromhex("81090606ff")
	InformationDisplay = bytearray.fromhex("81097e0118ff")
	VideoFormat = bytearray.fromhex("81090623ff")
	ColorSystem = bytearray.fromhex("81097e0103ff")
	IRReceive = bytearray.fromhex("81090608ff")
	IRCondition = bytearray.fromhex("81090634ff")
	PanTiltMaxSpeed = bytearray.fromhex("81090611ff")
	PanTiltPos = bytearray.fromhex("81090612ff")
	PanTiltMode = bytearray.fromhex("81090610ff")

	BlockLens = bytearray.fromhex("81097e7e00ff")
	BlockControl = bytearray.fromhex("81097e7e01ff")
	BlockOther = bytearray.fromhex("81097e7e02ff")
	BlockEnlargement = bytearray.fromhex("81097e7e03ff")
	BlockEnlargement2 = bytearray.fromhex("81097e7e04ff")
	BlockEnlargement3 = bytearray.fromhex("81097e7e05ff")

class Lookups():
	VideoFormats = {
		0: "1080p59",
		1: "1080p29",
		2: "1080i59",
		3: "720p59",
		4: "720p29",
		8: "1080p50",
		0xA: "1080p25",
		0xB: "1080i50",
		0xC: "720p50",
		0xD: "720p25"
	}
	ColorSystems = {
		0: "HDMI-YUV",
		1: "HDMI-GBR",
		2: "DVI-GBR",
		3: "DVI-YUV"
	}
	Iris = {
		0x11: "F1.8",
		0x10: "F2.0",
		0xf: "F2.4",
		0xe: "F2.8",
		0xd: "F3.4",
		0xc: "F4",
		0xb: "F4.8",
		0xa: "F5.6",
		9: "F6.8",
		8: "F8",
		7: "F9.6",
		6: "F11",
		5: "F14",
		0: "CLOSE"
	}
	Shutter = {
		6: "1/1",
		7: "2/3",
		8: "1/2",
		9: "1/3",
		0xa: "1/4",
		0xb: "1/6",
		0xc: "1/8",
		0xd: "1/10",
		0xe: "1/15",
		0xf: "1/20",
		0x10: "1/30",
		0x11: "1/50",
		0x12: "1/60",
		0x13: "1/90",
		0x14: "1/100",
		0x15: "1/125",
		0x16: "1/180",
		0x17: "1/250",
		0x18: "1/350",
		0x19: "1/500",
		0x1a: "1/725",
		0x1b: "1/1000",
		0x1c: "1/1500",
		0x1d: "1/2000",
		0x1e: "1/3000",
		0x1f: "1/4000",
		0x20: "1/6000",
		0x21: "1/10000"
	}
