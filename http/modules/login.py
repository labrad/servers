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

class LoginPage(Element):
    loader = XMLFile('modules/login.xml')
    
    def __init__(self, cxn, request):
        super(LoginPage, self).__init__()
 

    
        
class LoginFuncs():
    '''
    This is the class that handles the backend functions
    '''
    def __init__(self):
        pass

page_funcs = LoginFuncs()     
page_factory = LoginPage
