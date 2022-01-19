import asyncio
import socket
import logging
import threading
import struct
import re
import ipaddress
from sony_visca import aioudp
from sony_visca.visca_commands import Inquiry, Command
from sony_visca.myqueue import MyQueue

socket.setdefaulttimeout(2)

LOGGER = logging.getLogger("ptz.visca")


class LoopThread(threading.Thread):
	"""Thread to run an event loop in"""

	def __init__(self):
		super().__init__()
		self.loop = None
		self.ready = threading.Event()

	def run(self):
		self.loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self.loop)
		self.ready.set()
		self.loop.run_forever()

	def stop(self):
		self.loop.call_soon_threadsafe(self.loop.stop)
		LOGGER.info("Waiting for event loop to stop")
		self.join()

	def wait_ready(self):
		self.ready.wait()


class ViscaIPCamera:
	_LOOP_THREAD = None
	_LOCAL_SOCK = None
	_CONNECTED_CAMS = 0

	def __init__(self, name, ip, mac, netmask="255.255.255.0", gateway="0.0.0.0", port=52381, device_id=None, simple_visca=False):
		self.sequenceNumber = 1 # starts at 1?
		self.name = name
		self.ip = ip
		self.mac = mac # mac using dashes to seperate
		self.netmask = netmask
		self.gateway = gateway
		self.port = port
		self.is_connected = False
		self.device_id = device_id
		self.simple_visca = simple_visca
		self._remote_sock = None
		self._queue_loop = None  # Handle to the Task running the queue processing loop

	def __str__(self):
		return f"{self.name}({self.mac}) {self.ip}"

	def __repr__(self):
		return f"<ViscaIPCamera name={self.name!r} mac={self.mac!r}>"

	def initialise(self):
		"""Initialise this camera on the event loop"""
		if not self._LOOP_THREAD:
			# If we don't have an event loop, create one
			self.__class__._LOOP_THREAD = LoopThread()
			self._LOOP_THREAD.start()
			self._LOOP_THREAD.wait_ready()
			LOGGER.info("Started camera event loop")
		self.__class__._CONNECTED_CAMS += 1
		future = asyncio.run_coroutine_threadsafe(self._initialise(), self._LOOP_THREAD.loop)
		return future.result()

	async def _initialise(self):
		"""Setup the async sockets"""
		self.cmd_queue = MyQueue()
		if self._LOCAL_SOCK is None:
			# The first camera initialised needs to open the local socket
			self.__class__._LOCAL_SOCK = await aioudp.open_local_endpoint("0.0.0.0", 52381)
			LOGGER.info("Opened local UDP socket")
		self._remote_sock = await aioudp.open_remote_endpoint(self.ip, self.port)
		LOGGER.info("Opened remote UDP socket to cam %s", self.ip)
		try:
			if not self.simple_visca:
				await self.resetSequenceNumber()
			self.is_connected = True
		except asyncio.TimeoutError:
			LOGGER.warning("Timeout trying to reset sequence number on camera %s", self.ip)

	def close(self):
		"""Close communication sockets, and event loop if this is the last camera
		We have to teardown the event loop when the last camera is torn down as we're hiding async from the user
		"""
		future = asyncio.run_coroutine_threadsafe(self._close(), self._LOOP_THREAD.loop)
		future.result()
		LOGGER.info("Closed remote UDP socket to cam %s", self.ip)
		self.__class__._CONNECTED_CAMS -= 1
		if self._CONNECTED_CAMS == 0:
			# If this is the last camera, shutdown the local socket and the event loop
			future = asyncio.run_coroutine_threadsafe(self._close_local(), self._LOOP_THREAD.loop)
			future.result()
			LOGGER.info("Closed local UDP socket")
			self._LOOP_THREAD.stop()
			LOGGER.info("Stopped event loop")
			self.__class__._LOOP_THREAD = None

	async def _close(self):
		"""Close this camera"""
		if self._queue_loop is not None:
			self.cmd_queue.trigger_shutdown()
			LOGGER.debug("Waiting for queue watcher to exit...")
			await asyncio.gather(self._queue_loop)
		self._remote_sock.close()
		self._remote_sock = None
		self.is_connected = False

	async def _close_local(self):
		"""Close the local socket"""
		self._LOCAL_SOCK.close()
		self.__class__._LOCAL_SOCK = None

	def setIP(self, ip=None, netmask=None, gateway=None, name=None):
		"""Set IP address of camera
		Currently only compatible with Sony cameras.
		"""
		# name must be up to 8 alphanumeric characters (and blank)
		if not ip:
			ip = self.ip
		if not netmask:
			netmask = self.netmask
		if not gateway:
			gateway = self.gateway
		if not name:
			name = self.name
		mac_bytes = bytes(self.mac, encoding="utf-8")
		command = (b"\x02MAC:"+mac_bytes+b"\xFFIPADR:"+bytes(ip, encoding="utf-8")+
					b"\xFFMASK:"+bytes(netmask, encoding="utf-8")+b"\xFFGATEWAY:"+bytes(gateway, encoding="utf-8")+
					b"\xFFNAME:"+bytes(name, encoding="utf-8")+b"\xFF\x03")
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
			sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
			sock.sendto(command, ("<broadcast>", 52380))
			LOGGER.info("setIP sent to %r, new data: ip=%r, name=%r", self.mac, ip, name)
			resp = sock.recv(1024)
			LOGGER.debug("Raw response from setIP: %r", resp)
			assert resp == b"\x02ACK:" + mac_bytes + b"\xff\x03", "setIP response is not as expected!"

	def queueCommands(self, *args, override=True):
		"""Queue one or more messages to be sent, generally this overrides the last command unless override=False"""
		future = asyncio.run_coroutine_threadsafe(self._queueCommands(*args, override=override), self._LOOP_THREAD.loop)
		future.result()

	async def _queueCommands(self, *args, override=True):
		LOGGER.debug("Putting on the queue: %r", args)
		if override:
			self.cmd_queue.clear_and_put(*args)
		else:
			self.cmd_queue.put_many(*args)
		if self._queue_loop is None:
			# Start the queue watcher if not already started
			self._queue_loop = asyncio.create_task(self._watchQueue())

	async def _watchQueue(self):
		"""Watch and process the command queue for this camera."""
		LOGGER.info("Starting queue watcher")
		while True:
			cmd = await self.cmd_queue.get()
			if cmd is None:
				LOGGER.debug("Received trigger to stop the queue watcher")
				break
			LOGGER.debug("Sending command cmd: %r", cmd)
			try:
				await self._sendCommand(cmd)
			except Exception:
				LOGGER.exception("Command failed: %r", cmd)
			# We should really call task done after a get() but my clearing of the queue in MyQueue breaks the counting.
			#   So for now we'll just not bother given we never use join()
			# self.cmd_queue.task_done()
		LOGGER.info("Queue watcher exited")

	def sendCommand(self, command, skipCompletion=False):
		"""Send a command to the camera using the event loop"""
		future = asyncio.run_coroutine_threadsafe(
			self._sendCommand(command), self._LOOP_THREAD.loop
		)
		return future.result()

	async def _sendCommand(self, command):
		# for general commands (payload type 0100), command should be bytes
		length = len(command.value).to_bytes(2, 'big')
		if not self.simple_visca:
			command.value = b"\x01\x00" + length + self.sequenceNumber.to_bytes(4, 'big') + command.value
		data = await self._sendRawCommand(command.value, **command.kwargs) # TODO: deal with udp packets getting lost and sequence number desyncing (see manual)
		self.sequenceNumber += 1
		command.result = data
		return data

	def inquire(self, command):
		"""Send an inquiry message (must be wrapped in a Command()"""
		future = asyncio.run_coroutine_threadsafe(self._inquire(command), self._LOOP_THREAD.loop)
		return future.result()

	async def _inquire(self, command):
		# No acknowledge messages provided for inquiries
		command.skipCompletion = True
		return await self._sendCommand(command)

	async def resetSequenceNumber(self):
		"""Reset the Sony camera sequence number"""
		self.sequenceNumber = 1
		await self._sendRawCommand(
			bytearray.fromhex('02 00 00 01 00 00 00 01 01'), skipCompletion=True, raise_on_timeout=True
		)

	def getPos(self):
		data = self.inquire(Command(Inquiry.PanTiltPos))
		pan = (data[10] << 12) | (data[11] << 8) | (data[12] << 4) | data[13]
		tilt = (data[14] << 12) | (data[15] << 8) | (data[16] << 4) | data[17]
		LOGGER.debug("Got positions, Pan: %0.4x Tilt: %0.4x", pan, tilt)
		return (pan, tilt)

	async def _receive(self):
		# receive() wrapped in a wait_for to simulate sync socket timeouts (for when camera goes AWOL)
		data = await asyncio.wait_for(self._LOCAL_SOCK.receive(self.ip), timeout=1)
		if b"NAK" in data:
			LOGGER.error("Command failed with error: %r", data)
		if len(data) > 10:
			if data[8] == 0x90:
				# acknowledged (0x4Y) / completion (0x5Y) / error message (0x6Y), Y = socket number
				if (data[9] & 0xf0) == 0x40:
					LOGGER.debug("Command acknowledged successfully")
				if (data[9] & 0xf0) == 0x50:
					LOGGER.debug("Command completed successfully")
				if (data[9] & 0xf0) == 0x60:
					LOGGER.error("Command failed with error: %r", data)
					error = {0x01: "Message length error", 0x02: "Syntax Error", 0x03: "Command buffer full",
							 0x04: "Command canceled", 0x05: "No socket", 0x41: "Command not executable"}
					LOGGER.error("Formatted: %s", error.get(data[10], "Unknown"))
		else:
			if data == b'\x02\x01\x00\x01\x00\x00\x00\x00\x01':
				LOGGER.debug("Successfully reset sequence number")
			else:
				LOGGER.error("Returned data was too short?")
		return data

	async def _sendRawCommand(self, command, skipCompletion=False, raise_on_timeout=False):
		# this sends a command and waits for a response, note it does NOT calculate / use the sequence number
		# command should be a bytes object
		LOGGER.debug("Sending to %s: %r", self.ip, command)
		self._remote_sock.send(command)

		# FIXME: hack to workaround currently being unable to receive from non Sony cameras
		if self.simple_visca:
			return None

		LOGGER.debug("Waiting for _receive...")
		try:
			data = await self._receive()  # acknowledge
			if skipCompletion:
				return data
			data = await self._receive()  # completion
			return data
		except asyncio.TimeoutError:
			LOGGER.error("Timeout waiting for data from camera %s!", self.ip)
			# TODO: may be nice to set is_connected or similar False here and update UI to show warning. Reset on next
			#  success. Bare in mind the implications of setting is_connected to False in other code
			if raise_on_timeout:
				raise

	@classmethod
	def discoverCameras(cls):
		# UDP socket, enable broadcast, and socket reuse (hah if even that worked)
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
		s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
		s.settimeout(1)

		try:
			s.bind(("", 52380))

			discoverCmd = b"\x02ENQ:network\xFF\x33"
			LOGGER.debug("Sending discover...")
			s.sendto(discoverCmd, ('<broadcast>', 52380))
			cameras = []
			try:
				while True:
					raw, addr = s.recvfrom(1024)
					if raw == discoverCmd:
						continue
					data = raw.split(b'\xFF')
					name = data[7][5:].decode("utf-8")
					mac = data[0][5:].decode("utf-8")
					LOGGER.info("Found camera '%s' (%s) at IP %s", name, mac, addr[0])
					cameras.append(cls(name, addr[0], mac))
			except socket.timeout:
				LOGGER.debug("End Sony discover")
			return cameras
		finally:
			s.close()

	@classmethod
	def discoverNonSony(cls):
		"""Discover non-Sony PTZ cameras over multicast"""
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
		responses = []
		try:
			# sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			remote_addr = ipaddress.ip_address("239.255.255.251")
			sock.setsockopt(
				socket.IPPROTO_IP,
				socket.IP_ADD_MEMBERSHIP,
				struct.pack("4sl", remote_addr.packed, socket.INADDR_ANY),
			)
			sock.bind(("", 8005))
			sock.sendto(b"SEARCH * UPGRADE", ("239.255.255.251", 8005))
			try:
				while True:
					data, addr = sock.recvfrom(1024)
					LOGGER.debug("Discover got data: %r", data)
					responses.append(data)
			except socket.timeout:
				LOGGER.debug("End non-Sony discover")
		finally:
			sock.close()

		regex = re.compile(
			r"REPLY OK\s+Client ID:(?P<client_id>[A-Fa-f0-9]{32})?\s+Device ID:(?P<device_id>[A-Fa-f0-9]{32})\s+DHCP=(?P<dhcp>\d).*IP=(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+MASK=(?P<mask>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+GATEWAY=(?P<gateway>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+MAC=(?P<mac>([A-Fa-f0-9]{2}[:-]){5}[A-Fa-f0-9]{2})\s+FDNS=(?P<dns>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
			re.DOTALL,
		)
		found = []
		for resp in responses:
			mo = regex.match((resp.decode()))
			if mo:
				info = mo.groupdict()
				# We don't seem to get camera names back from discover here so bodge a bit of device id
				LOGGER.info("Found camera '%s' (%s) at IP %s", info["device_id"], info["mac"], info["ip"])
				found.append(cls(
					info["device_id"][:8],
					info["ip"],
					info["mac"],
					netmask=info["mask"],
					gateway=info["gateway"],
					port=1259,
					device_id=info["device_id"],
					simple_visca=True,
				))
		return found
