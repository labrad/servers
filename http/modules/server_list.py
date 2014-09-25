#!/usr/bin/python

from twisted.internet.defer import inlineCallbacks, returnValue, Deferred
from twisted.web.template import flattenString, Element, renderer, XMLFile, tags
from twisted.web.client import getPage
import datetime
import time


import sys
# sys.path.insert(1,'U:\\Josh\\labrad-servers\\servers\\http')
from http_server import render_safe
#
# This file can be used as a template for new status pages.  All you need to is
# to create a class which can be flattened by twisted.web.template.flattenString
# and assign it to the module global "page_factory".  Then drop it in the
# labrad/servers/http/modules directory and it will automatically be served up.   
#

class ServerListPage(Element):
    loader = XMLFile('modules/server_list.xml')
    
    def __init__(self, cxn, request):
        super(ServerListPage, self).__init__()
        self._cxn = cxn
        self.cryo_name = request.args.get('cryo', [''])[-1]
        self.max_entries = int(request.args.get('maxentries', ['25'])[-1])
        self.favs_path = ['', 'Servers', 'Server List']
        # print "FOUND SERVER NAME AT: ",find_node_server(cxn)
        self.node = self._cxn[find_node_server(cxn)]

    # @inlineCallbacks
    # def get_server(self):
        # name = yield self._cxn.manager.node_name()
        # self.node = self._cxn["node_%s" % name.lower()+"_laptop"]
        
    @inlineCallbacks
    def get_favourites(self):
        node = find_node_name(self._cxn)
        p = self._cxn.registry.packet()
        p.cd(self.favs_path)
        p.get(node, False, False)
        rv = yield p.send()
        print "THE WHITELIST IS!!!!! ",rv.get
        returnValue(rv.get)
        
    @inlineCallbacks
    def get_all_servers(self):
        all_servers = yield self.node.available_servers()
        returnValue(all_servers)
    
    @inlineCallbacks
    def run_server(self):
        print "Will Run Server"
    
    @inlineCallbacks
    def get_running_servers(self):
        running_servers_tuple = yield self.node.running_servers()
        running_servers = []
        for entry in map(list,running_servers_tuple):
            running_servers.append(entry[0])
        returnValue(running_servers)
     
    # @inlineCallbacks
    # def func(self):

                
    @render_safe
    @inlineCallbacks
    def server_entries(self, request, tag):
        # yield self.get_server()
        serverdata = yield self.get_all_servers()
        runningservers = yield self.get_running_servers()
        # running_servers = []
        # for entry in map(list,runningservers):
            # running_servers.append(entry[0])
        print "\nRUNNING SERVERS ARE: ",runningservers
        #rv = [tag.clone().fillSlots(servername=tags.b("Server Name"),stopper_class="btn btn-inverse",starter_text="s",starter_class='btn btn-default',srvstop='stop')]
        rv = []
        for idx,entry in enumerate(serverdata):
            servername = entry
            if entry in runningservers:
                rv.append(tag.clone().fillSlots(servername=servername,stopper_class = "btn btn-danger btn-block",starter_text="Started",starter_class='btn btn-success btn-block',srvstop="stp%d"%(idx)))
            else:
                rv.append(tag.clone().fillSlots(servername=servername,stopper_class = "btn btn-inverse btn-block",starter_text="Start",starter_class='btn btn-primary btn-block',srvstop="stp%d"%(idx)))
        returnValue(rv)
    
    @render_safe        
    # @inlineCallbacks
    def topstuff(self, request, tag):    
        tnow = str(time.time())
        rv = [tag.clone().fillSlots(topcont=tnow)]
        return(rv)
        
    @render_safe
    @inlineCallbacks
    def favourite_entries(self, request, tag):
        favourite_data = yield self.get_favourites()
        if not favourite_data:
            error_string = "Entry for '%s' not found in registry under path %s" % (find_node_name(self._cxn), str(self.favs_path))
            print error_string
            rv = [tag.clone().fillSlots(favourite_name=tags.b(error_string))]
            returnValue(rv)
        runningservers = yield self.get_running_servers()
        rv = [tag.clone().fillSlots(favourite_name=tags.b("Server Name"),stopper_class="btn btn-inverse",starter_text="s",starter_class='btn btn-default')]
        for entry in favourite_data:
            whitelistname = entry
            if entry in runningservers:
                rv.append(tag.clone().fillSlots(favourite_name=entry,stopper_class = "btn btn-danger",starter_text="Started",starter_class='btn btn-success'))
            else:
                rv.append(tag.clone().fillSlots(favourite_name=entry,stopper_class = "btn btn-inverse",starter_text="Start",starter_class='btn btn-primary'))
        returnValue(rv)
        
class ServerListFuncs():
    '''
    This is the class that handles the backend functions
    '''
    def __init__(self):
        # self.agent =Agent()
        pass
        # self._cxn = cxn
        # self.node = self._cxn[find_node_server(cxn)]
        # print "\nTHE NODE SERVER IS CALLED: ", find_node_server(cxn)
    
    @inlineCallbacks
    def get_request(self,request,cxn):
        self._cxn = cxn
        self.req_uri = request.uri.split('/')[2]
        serverStr = request.content.read()
        serverStr = serverStr.replace('+',' ').split('=')[1]
        print "\n>>>>>>>>Request at: %s, for: %s \n"%(self.req_uri,serverStr)
        result = yield getattr(self,'handle_'+self.req_uri)(cxn,serverStr) #launches a method based on uri name
    
    @inlineCallbacks
    def handle_start(self,cxn,serverStr):
        # name = yield self._cxn.manager.node_name()
        # name = yield self._cxn.manager.node_name()
        # node = self._cxn["node_%s" % name.lower()]
        node = self._cxn[find_node_server(cxn)]
        print "\n RUNNING handle_start"
        rv = yield node.start(serverStr)
        # req = Request('GET','http://localhost:8881/server_list')
        # rv = Deferred()
        req =  yield getPage('http://localhost:8881/server_list')
        print "\n Ran start"
        returnValue(rv)
        
    @inlineCallbacks
    def handle_stop(self,cxn,serverStr):
        node = self._cxn[find_node_server(cxn)]
        # print "/n<<<<<<<<<<<<< in handle_stop"
        # name = yield self._cxn.manager.node_name()
        # node = self._cxn["node_%s" % name.lower()+'_laptop']
        rv = yield node.stop(serverStr)
        req =  yield getPage('http://localhost:8881/server_list')
        print "\n Ran stop"
        returnValue(rv)

        
def find_node_server(cxn):
    for server in cxn.servers:
        print "\n CXN.SERVERS:, ", server
        if server.startswith("node"):
            server = server.replace(' ','_').replace('-','_').lower()
            print "\n IN NODE SERVER FINDER, FOUND: ",server
            return(server)
            
def find_node_name(cxn):
    return find_node_server(cxn)[5:]
        
page_funcs = ServerListFuncs()     
page_factory = ServerListPage
