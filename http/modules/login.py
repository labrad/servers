#!/usr/bin/python

from twisted.internet.defer import inlineCallbacks, returnValue, Deferred
from twisted.web.template import flattenString, Element, renderer, XMLFile, tags
from twisted.web.client import getPage
import datetime
import time
import sys

sys.path.append('C:\\Program Files (x86)\\Google\\google_appengine') #This is maybe in a silly place
from oauth2client.appengine import OAuth2Decorator
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.client import AccessTokenRefreshError
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
from oauth2client.appengine import oauth2decorator_from_clientsecrets
from google.appengine.ext.webapp.util import login_required



# sys.path.insert(1,'U:\\Josh\\labrad-servers\\servers\\http')
from http_server import render_safe, CLIENT_ID, state, APPLICATION_NAME, ALLOWED_IDS
#
# This file can be used as a template for new status pages.  All you need to is
# to create a class which can be flattened by twisted.web.template.flattenString
# and assign it to the module global "page_factory".  Then drop it in the
# labrad/servers/http/modules directory and it will automatically be served up.   
#
decorator = oauth2decorator_from_clientsecrets('client_secrets.json', scope='https://www.googleapis.com/auth/plus')
'''
THe example here is essential for figuring out what's going on:
https://developers.google.com/+/quickstart/python
'''
LOGIN_ID = None
class LoginPage(Element):
    loader = XMLFile('modules/login.xml')
    
    def __init__(self, cxn, request):
        super(LoginPage, self).__init__()
        
    @render_safe
    def client_stuff(self, request, tag):
         rv = [tag.clone().fillSlots(CLIENT_ID=CLIENT_ID,state=state,APPLICATION_NAME=APPLICATION_NAME)]
         return(rv)
 
 

    
        
class LoginFuncs():
    '''
    This is the class that handles the backend functions
    '''
    def __init__(self):
        pass
        
    def get_request(self,request,cxn):
        '''
        The unfortunately named get_request, proccessess a POST request and runs 
        the appropriate handle function based on the uri
        '''
        self._cxn = cxn
        
        self.req_uri = request.uri.split('/')[2]
        code = request.content.read()
        print "\n***************I AM IN get_request() the uri is: ",self.req_uri 
        print "\n*************** the code is: ", code
        # serverStr = request.content.read()
        # serverStr = serverStr.replace('+',' ').split('=')[1]
        # print "\n>>>>>>>>Request at: %s, for: %s \n"%(self.req_uri,serverStr)
        # result = yield getattr(self,'handle_'+self.req_uri)(cxn) #launches a method based on uri name
        getattr(self,'handle_'+self.req_uri)(cxn,code) #launches a method based on uri name
    
    def handle_connect(self,cxn,code):
        print "\nI am handling the connection! The code is:",code
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
        gplus_id = credentials.id_token['sub']
        LOGIN_ID = int(gplus_id)
        print "\n I THINK IM ACTUALLY CONNECTED: ", LOGIN_ID, type(LOGIN_ID), LOGIN_ID in ALLOWED_IDS
        return LOGIN_ID
        # self.decorator = oauth2decorator_from_clientsecrets('client_secrets.json', scope='https://www.googleapis.com/auth/plus')
   
    def handle_test(self,cxn,code):
        print "I have priviledges to run this"
        
page_funcs = LoginFuncs()     
page_factory = LoginPage
