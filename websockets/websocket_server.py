"""WebSocket Echo.

Install: pip install twisted txws

run as python websocket_server.py

Connect to at localhost:8076/
"""
from twisted.application import strports # pip install twisted
from twisted.application.service import Application
from twisted.internet.protocol import Factory, Protocol
from twisted.python import log
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
 
from txws import WebSocketFactory # pip install txws
import numpy as np
from ast import literal_eval


def create_2d_test_data(indep= 500,dep =300):
    '''
    creates data_vault style 2D data
    :param indep: number of independent points
    :param dep: number of dependent points
    :return: the correct shaped array
    '''

    indeps = np.arange(indep)
    foo=[]
    for i in range(indep):
        for j in range(dep):
            foo.append([i,j])
    foo_arr = np.asarray(foo)
    deps = np.random.randint(256,size=(foo_arr.shape[0],3))
    return np.hstack([foo_arr,deps])

class CxnFactory(Factory):
    '''
    This is a factory but with a client connection
    '''
    def __init__(self,cxn):
        self.cxn = cxn

class DataVaultProtocol(Protocol):
    """Protocol for handling request to the data_vault server"""

    def connectionMade(self):
        log.msg("Connection made, connected to: ",self.factory.cxn)
        self.cxn = self.factory.cxn
        self.dv = self.cxn.data_vault

    @inlineCallbacks
    def dataReceived(self, data):
        parsed = data.split('.')
        if parsed[0] == "cd":
            log.msg("Got a dv cd request")
            pv = yield self.dv.cd(literal_eval(parsed[1]))
            self.transport.write("Current Directory: " + str(pv))
        elif parsed[0] == "dir":
            log.msg("Got a request for dv dir")
            current_dir = yield self.dv.dir([])
            self.transport.write(str(current_dir))
        elif parsed[0] == "get":
            log.msg("Got a request for dv get")
        elif parsed[0] == "open":
            log.msg("Got a request for dv open")
        else:
            log.msg("Got an unsupported request")
            self.transport.write("I'm sorry, I can't do that")

from labrad.server import LabradServer, setting

class WebSocketServer(LabradServer):
    name = "Web Socket Server"    # Will be labrad name of server

    def initServer(self):
        application = Application("ws-streamer")
        data_vaultfactory = CxnFactory(self.client)
        data_vaultfactory.protocol = DataVaultProtocol
        reactor.listenTCP(8076, WebSocketFactory(data_vaultfactory))

__server__ = WebSocketServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
