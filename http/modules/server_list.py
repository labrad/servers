#!/usr/bin/python

from twisted.internet.defer import inlineCallbacks, returnValue, Deferred
from twisted.web.template import flattenString, Element, renderer, XMLFile, tags
import datetime


import sys
sys.path.insert(1,'U:\\Josh\\labrad-servers\\servers\\http')
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
    def get_whitelist(self):
        p = self._cxn.registry.packet()
        p.cd(self.white_list_path)
        p.get('Ivan')
        rv = yield p.send()
        print "THE WHITELIST IS!!!!! ",rv.get
        returnValue(rv.get)
        
    @inlineCallbacks
    def get_all_servers(self):
        node = self._cxn.node_ivan
        all_servers = yield node.available_servers()
        returnValue(all_servers)
          
    @render_safe
    @inlineCallbacks
    def serverentries(self, request, tag):
        serverdata = yield self.get_all_servers()
        rv = [tag.clone().fillSlots(servername=tags.b("Server"),divid="something")]
        for idx,entry in enumerate(serverdata):
            servername = entry
            rv.append(tag.clone().fillSlots(servername=servername,divid = "srv%d"%(idx)))
            print "srv%d"%(idx)
        returnValue(rv)
        
    @render_safe
    @inlineCallbacks
    def whitelistentries(self, request, tag):
        whitelistdata = yield self.get_whitelist()
        rv = [tag.clone().fillSlots(whitelistname=tags.b("Server"))]
        for entry in whitelistdata:
            whitelistname = entry
            rv.append(tag.clone().fillSlots(whitelistname=whitelistname))
        returnValue(rv)
        

        
        
page_factory = ServerListPage
