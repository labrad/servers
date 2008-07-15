from labrad.server import LabradServer

class DeviceManager(LabradServer):
    name = "Device Manager"
    
    def initServer(self):
        gpibDevices = {}
        serialDevices = {}
    
    @messageHandler("GPIB Device Connected",
                    server='s', channel='s', mfr='s', model='s')
    def gpib_device_connected(self, c, server, channel,
                              mfr='<unknown>', model='<unknown>'):
        self.gpibDevices[server, channel] = [mfr, model, False]
        msg = "GPIB Device Connected: %s, %s" % (mfr, model)
        self.client.manager.send_named_message(msg, (server, channel))
    
    @messageHandler("GPIB Device Connected", server='s', channel='s')
    def gpib_device_disconnected(self, c, server, channel):
        if (server, channel) in self.gpibDevices:
            del self.gpibDevices[server, channel]
        msg = "GPIB Device Disconnected: %s, %s" % (mfr, model)
        self.client.manager.send_named_message(msg, (server, channel))
    
    @setting(1, unclaimed_only='b')
    def list_gpib_devices(self, c, unclaimed_only=True):
        pass
    
    @setting(2)
    def claim_device(self, c, server, channel):
        self.gpibDevices[server, channel][2] = True
    

# device: type, server, channel, info
# type (s): (GPIB|Serial)
# server (s): e.g. ADR GPIB Bus, DR GPIB Bus, Electronics GPIB Bus, etc.
# channel (s): e.g. COM2, 5
# info (*s): for GPIB: [mfr, model]; for serial: [nothing]

# when a new device server connects, ask manager for a list of devices
# if any of them match the criteria, claim them
# thereafter, get messages notifying us of this device type

# when the device manager connects, tell all existing busses to announce their devices