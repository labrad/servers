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
    loader = XMLFile('modules\\server_list.xml')
    
    def __init__(self, cxn, request):
        super(ServerListPage, self).__init__()
        self._cxn = cxn
        self.cryo_name = request.args.get('cryo', [''])[-1]
        self.max_entries = int(request.args.get('maxentries', ['25'])[-1])
        self.white_list_path = ['', 'Servers', 'Server List' ]
        

    @inlineCallbacks
    def get_server(self):
        name = yield self._cxn.manager.node_name()
        self.node = self._cxn["node_%s" % name.lower()+'_laptop']
        
    @inlineCallbacks
    def get_whitelist(self):
        p = self._cxn.registry.packet()
        p.cd(self.white_list_path)
        p.get('Ivan')
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
    def foo(self,request):
        d  = Deferred()
        print "\nI AM IN FOO\n"
        return d
        
    @inlineCallbacks
    def bar(self,request):
        print "\nI AM IN BAR\n"
        return request
        
    @render_safe
    @inlineCallbacks
    def serverentries(self, request, tag):
        yield self.get_server()
        serverdata = yield self.get_all_servers()
        rv = [tag.clone().fillSlots(servername=tags.b("Server"),srvname="s",srvstart="s")]
        for idx,entry in enumerate(serverdata):
            servername = entry
            rv.append(tag.clone().fillSlots(servername=servername,srvname = "nm%d"%(idx),srvstart="strt%d"%(idx)))
            # print "srv%d"%(idx)
        returnValue(rv)
    
    @render_safe        
    # @inlineCallbacks
    def topstuff(self, request, tag):    
        tnow = str(time.time())
        rv = [tag.clone().fillSlots(topcont=tnow)]
        return(rv)
        
    @render_safe
    @inlineCallbacks
    def whitelistentries(self, request, tag):
        whitelistdata = yield self.get_whitelist()
        rv = [tag.clone().fillSlots(whitelistname=tags.b("Server"))]
        for entry in whitelistdata:
            whitelistname = entry
            rv.append(tag.clone().fillSlots(whitelistname=whitelistname))
        returnValue(rv)
        
class ServerListFuncs():
    '''
    This is the class that handles the backend functions
    '''
    def __init__(self):
        # self.agent =Agent()
        pass
    
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
        name = yield self._cxn.manager.node_name()
        node = self._cxn["node_%s" % name.lower()+'_laptop']
        print "\n RUNNING handle_start"
        rv = yield node.start(serverStr)
        # req = Request('GET','http://localhost:8881/server_list')
        # rv = Deferred()
        req =  yield getPage('http://localhost:8881/server_list')
        print "\n Ran it"
        returnValue(rv)
        
    @inlineCallbacks
    def handle_stop(self,cxn,serverStr):
        name = yield self._cxn.manager.node_name()
        node = self._cxn["node_%s" % name.lower()+'_laptop']
        
page_funcs = ServerListFuncs()       
page_factory = ServerListPage
