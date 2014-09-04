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

class BootstrapPage(Element):
    loader = XMLFile('modules/bootstrap_demo.xml')
    
    def __init__(self, cxn, request):
        super(BootstrapPage, self).__init__()
        self.navbar_names = ["Nav Folders","Stuff 1","Stuff 2","Downlaod","Trace Mem."]
     
    widgetData = ['gadget', 'contraption', 'gizmo', 'doohickey'] 
    
    @render_safe
    def render_navbar(self, request, tag):
        # yield self.get_server()
        # running_servers = []
        # for entry in map(list,runningservers):
            # running_servers.append(entry[0])
        print "\nItems in navbar are: ", self.navbar_names
        for ent in self.navbar_names:
            yield tag.clone().fillSlots(thing = ent)
        # rv = [tag.clone().fillSlots(servername=tags.b("Server"))]
        # for idx,entry in enumerate(serverdata):
            # servername = entry
            # if entry in runningservers:
                # rv.append(tag.clone().fillSlots(servername=servername,srvname = "nm%d"%(idx),srvstart="strt%d"%(idx),starter='Started',srvstop="stp%d"%(idx)))
            # else:
                # rv.append(tag.clone().fillSlots(servername=servername,srvname = "nm%d"%(idx),srvstart="strt%d"%(idx),starter='Start',srvstop="stp%d"%(idx)))
        # returnValue(rv)
    # @render_safe
    # @inlineCallbacks
    @render_safe    
    def widgets(self, request, tag):
        # rv = [tag.clone().fillSlots(servername=tags.b("Server"))]
        for widget in self.navbar_names:
            yield (tag.clone().fillSlots(widgetName=widget))
        
        
class BootstrapFuncs():
    '''
    This is the class that handles the backend functions
    '''
    def __init__(self):
        pass

        
page_funcs = BootstrapFuncs()     
page_factory = BootstrapPage
