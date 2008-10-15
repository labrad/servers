from twisted.internet.defer import DeferredList, DeferredLock
from twisted.internet.reactor import callLater

from labrad.server import (LabradServer, setting,
                           inlineCallbacks, returnValue)

UNKNOWN = '<unknown>'

def parseIDNResponse(s):
    """Parse the response from *IDN? to get mfr and model info."""
    mfr, model, ver, rev = s.split(',')
    return mfr.strip() + ' ' + model.strip()

class DeviceManager(LabradServer):
    """Manages autodetection and identification of GPIB devices.

    The device manager listens for "GPIB Device Connect" and
    "GPIB Device Disconnect" messages coming from all GPIB busses.
    It attempts to identify the connected devices and forward the
    messages on to servers interested in particular devices.  For
    devices that cannot be identified by *IDN? in the usual way,
    servers can register an identification setting to be called
    by the device manager to properly identify the device.
    """
    
    name = 'GPIB Device Manager'
    
    @inlineCallbacks
    def initServer(self):
        self.knownDevices = {}
        self.deviceServers = {}
        self.identFunctions = {}
        self.identLock = DeferredLock()
        mgr = self.client.manager
        # named messages are sent with source ID first, which we ignore
        connect_func = lambda c, (s, payload): self.gpib_device_connect(*payload)
        disconnect_func = lambda c, (s, payload): self.gpib_device_disconnect(*payload)
        self._cxn.addListener(connect_func, source=mgr.ID, ID=10)
        self._cxn.addListener(disconnect_func, source=mgr.ID, ID=11)
        yield mgr.subscribe_to_named_message('GPIB Device Connect', 10, True)
        yield mgr.subscribe_to_named_message('GPIB Device Disconnect', 11, True)
        yield self.refreshDeviceLists()
        
    @inlineCallbacks
    def refreshDeviceLists(self):
        """Ask all GPIB busses for their available GPIB devices."""
        yield self.client.refresh()
        servers = [s for n, s in self.client.servers.items()
                     if ('gpib_bus' in n) and ('list_devices' in s.settings)]
        names = [s._labrad_name for s in servers]
        print 'pinging servers:', names
        resp = yield DeferredList([s.list_devices() for s in servers])
        for name, (success, addrs) in zip(names, resp):
            if not success:
                print 'failed to get device list for:', name
            else:
                print 'server %s has devices: %s' % (name, addrs)
                for addr in addrs:
                    self.gpib_device_connect(name, addr)

    @inlineCallbacks
    def gpib_device_connect(self, server, channel):
        """Handle messages when devices connect."""
        print 'Device Connect:', server, channel
        if (server, channel) in self.knownDevices:
            return
        device, idnResult = yield self.lookupDeviceName(server, channel)
        if device == UNKNOWN:
            device = yield self.identifyDevice(server, channel, idnResult)
        self.knownDevices[server, channel] = (device, idnResult)
        # forward message if someone cares about this device
        if device in self.deviceServers:
            self.notifyServers(device, server, channel, True)
    
    def gpib_device_disconnect(self, server, channel):
        """Handle messages when devices connect."""
        print 'Device Disconnect:', server, channel
        if (server, channel) not in self.knownDevices:
            return
        device, idnResult = self.knownDevices[server, channel]
        del self.knownDevices[server, channel]
        # forward message if someone cares about this device
        if device in self.deviceServers:
            self.notifyServers(device, server, channel, False)
        
    @inlineCallbacks
    def lookupDeviceName(self, server, channel):
        """Try to send a *IDN? query to lookup info about a device."""
        yield self.client.refresh()
        p = self.client.servers[server].packet()
        p.address(channel).timeout(1).write('*IDN?').read()
        print 'sending *IDN? to', server, channel
        resp = None
        try:
            resp = (yield p.send()).read
            name = parseIDNResponse(resp)
        except Exception, e:
            print 'error sending *IDN? to', server, channel + ':', e
            name = UNKNOWN
        returnValue((name, resp))

    def identifyDevice(self, server, channel, idn):
        """Try to identify a new device with all ident functions."""
        @inlineCallbacks
        def _doIdentifyDevice(server, channel, idn):
            for target in list(self.identFunctions.keys()):
                name = yield self.tryIdentFunc(server, channel, idn, target)
                if name is None:
                    continue
                returnValue(name)
            returnValue(UNKNOWN)
        return self.identLock.run(_doIdentifyDevice, server, channel, idn)

    def identifyDevicesWithServer(self, target):
        """Try to identify all unknown devices with a new server."""
        @inlineCallbacks
        def _doServerIdentify(target):
            yield self.client.refresh()
            for (server, channel), (device, idn) in list(self.knownDevices.items()):
                if device != UNKNOWN:
                    continue
                name = yield self.tryIdentFunc(server, channel, idn, target)
                if name is None:
                    continue
                self.knownDevices[server, channel] = (name, idn)
                if name in self.deviceServers:
                    self.notifyServers(name, server, channel, True)
        return self.identLock.run(_doServerIdentify, target)        

    @inlineCallbacks
    def tryIdentFunc(self, server, channel, idn, target):
        """Try calling one registered identification function.

        If the identification succeeds, return the new name,
        otherwise return None.
        """
        setting, context = self.identFunctions[target]
        try:
            yield self.client.refresh()
            s = self.client[target]
            print 'trying to identify device', server, channel,
            print 'on server', target,
            print 'with *IDN?:', repr(idn)
            if idn is None:
                resp = yield s[setting](server, channel, context=context)
            else:
                resp = yield s[setting](server, channel, idn, context=context)
            if resp is not None:
                data = (target, server, channel, resp)
                print 'server %s identified device %s %s as "%s"' % data
                returnValue(resp)
        except Exception, e:
            print 'error during ident:', str(e)
    
    @setting(1, 'Register Server',
             device=['s', '*s'], messageID='w',
             returns='*(s{device} s{server} s{address}, b{isConnected})')
    def register_server(self, c, device, messageID):
        """Register as a server that handles a particular GPIB device(s).

        Returns a list with information about all matching devices that
        have been connected up to this point.  After registering,
        messages will be sent to the registered message ID whenever
        a matching device connects or disconnects.  The clusters sent
        in response to this setting and those sent as messages have the same
        format.  For messages, the final boolean indicates whether the
        device has been connected or disconnected, while in response to
        this function call, the final boolean is always true, since we
        only send info about connected devices.

        The device name is determined by parsing the response to a *IDN?
        query.  To handle devices that don't support *IDN? correctly, use
        'Register Ident Function' instead.
        """
        if isinstance(device, str):
            devices = [device]
        else:
            devices = device
        found = []
        for device in devices:
            servers = self.deviceServers.setdefault(device, [])
            servers.append({'target': c.source,
                            'context': c.ID,
                            'messageID': messageID})
            # send messages about all servers connected up to this point
            for (server, channel), (known_device, idnResult) in self.knownDevices.items():
                if device != known_device:
                    continue
                found.append((device, server, channel, True))
        return found

    @setting(2, 'Register Ident Function', setting=['s', 'w'], messageID='w')
    def register_ident_function(self, c, setting, messageID):
        """Specify a setting to be called to identify devices.

        This setting must accept either of the following:
        
            s, s, s: server, address, *IDN? response
            s, s:    server, address

        If a device returned a non-standard response to a *IDN? query
        (including possibly an empty string), then the first call signature
        will be used.  If the *IDN? query timed out, the second call
        signature will be used.  As a server writer, you must choose
        which of these signatures to support.  Note that if the device
        behavior is unpredictable (sometimes it returns a string, sometimes
        it times out), you may need to support both signatures.
        """
        self.identFunctions[c.source] = setting, c.ID
        # immediately try to identify all currently unknown devices
        callLater(0, self.identifyDevicesWithServer, c.source)

    @setting(10)
    def dump_info(self, c):
        return str(self.knownDevices), str(self.deviceServers)
    
    def notifyServers(self, device, server, channel, isConnected):
        """Notify all registered servers about a device status change."""
        for s in self.deviceServers[device]:
            rec = s['messageID'], (device, server, channel, isConnected)
            print 'sending message:', s['target'], s['context'], [rec]
            self.client._sendMessage(s['target'], [rec], context=s['context'])

    def serverDisconnected(self, ID, name):
        """Disconnect devices when a bus server disconnects."""
        for (server, channel) in list(self.knownDevices.keys()):
            if server == name:
                self.gpib_device_disconnect(server, channel)
    
    def expireContext(self, c):
        """Stop sending notifications when a context expires."""
        print 'expiring context:', c.ID
        # device servers
        deletions = []
        for device, servers in list(self.deviceServers.items()):
            # remove all registrations with this context
            servers = [s for s in servers if s['context'] != c.ID]
            self.deviceServers[device] = servers
            # if no one is left listening to this device, delete the list
            if not len(servers):
                deletions.append(device)
        for device in deletions:
            del self.deviceServers[device]

        # ident functions
        deletions = []
        for src, idents in list(self.identFunctions.items()):
            # remove all registrations with this context
            idents = [i for i in idents if i[1] != c.ID]
            self.identFunctions[src] = idents
            # if no one is left listening to this device, delete the list
            if not len(idents):
                deletions.append(src)
        for src in deletions:
            del self.identFunctions[src]

        

__server__ = DeviceManager()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
    
