#!/usr/bin/python
from __future__ import division

from twisted.web.server import Site, NOT_DONE_YET
from twisted.internet import reactor
from twisted.web.resource import Resource, IResource
from twisted.internet.defer import inlineCallbacks, returnValue, Deferred
from twisted.web.template import flattenString, Element, renderer, XMLFile, tags
from twisted.python.filepath import FilePath
import functools
import inspect
import labrad
import datetime
from zope.interface import implements

from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse as pwdb
from twisted.web.static import File
from twisted.web.guard import DigestCredentialFactory, HTTPAuthSessionWrapper

def render_safe(render_method):
    '''
    This decorator wraps a rendering function from a twisted web
    template with a version that just returns an error message if an
    exception is raised.  The idea is that if you have a web page that
    requests status from a bunch of labrad servers but one is broken
    or not started, the rest of the page will render correctly.

    We can handle something that returns a value or returns a deferred.
    '''
    def wrapper(obj, request, tag):
        def error_message(err):
            tag.clear()
            return tag("Unable to get content for replacement: %s, exception: %s" % ( render_method.__name__, err))

        try:
            rv = render_method(obj, request, tag)
            if isinstance(rv, Deferred):
                rv.addErrback(error_message)
            return rv
        except Exception as e:
            return error_message(e)

    functools.update_wrapper(wrapper, render_method)
    if wrapper.__doc__:
        wrapper.__doc__ += "\nWrapped by render_safe"
    else:
        wrapper.__doc__ = "Wrapped by render_safe"
    return renderer(wrapper)

class CryoStatusPage(Element):
    loader = XMLFile('cryo_log.xml')
    def __init__(self, cxn, request):
        super(CryoStatusPage, self).__init__()
        self._cxn = cxn
        self.cryo_name = request.args.get('cryo', [''])[-1]
        self.log_path = ['', 'Servers', 'Cryo Notifier', 'Log' ]

    @inlineCallbacks
    def get_log(self):
        p = self._cxn.registry.packet()
        p.cd(self.log_path)
        p.dir()
        p.cd([''])
        rv = yield p.send()
        subdirs, keys = rv['dir']
        p = self._cxn.registry.packet()
        p.cd(self.log_path)
        for k in keys:
            p.get(k, key=k)
        p.cd([''])
        values = yield p.send()
        result = []
        for k in keys:
            result.append((k,) + values[k])
        returnValue(result)

    @render_safe
    def name(self, request, tag):
        if self.cryo_name:
            return tag(self.cryo_name)
        else:
            return tag("<all>")

    @render_safe
    @inlineCallbacks
    def Diode(self, request, tag):
        '''
        This function has to be different than RuOx because lakeshore_dioes and lakeshore_ruox
        return data in different formats.  ruox returns a timestamp along with the temperature,
        diodes does not.
        '''
        server = self._cxn.lakeshore_diodes 
        p  = server.packet()
        p.select_device()
        p.temperatures()
        result = yield p.send()
        rv = []
        for idx, temp in enumerate(result['temperatures']):
            val = temp['K']
            if val<1:
                val = val*1000
                unit_str = 'mK'
            else:
                unit_str = 'K'
            rv.append(tag.clone().fillSlots(channel="%d: " % idx, temp="%.3f %s" % (val, unit_str)))
        returnValue(rv)
       

    @render_safe
    @inlineCallbacks
    def RuOx(self, request, tag):
        server = self._cxn.lakeshore_ruox
        p  = server.packet()
        p.select_device()
        p.temperatures()
        result = yield p.send()
        rv = []
        for idx, (temp, dt) in enumerate(result['temperatures']):
            val = temp['K']
            if val<1:
                val = val*1000
                unit_str = 'mK'
            else:
                unit_str = 'K'
            rv.append(tag.clone().fillSlots(channel="%d: " % idx, temp="%.3f %s" % (val, unit_str)))
        returnValue(rv)

    @render_safe
    @inlineCallbacks
    def timeouts(self, request, tag):
        p = self._cxn.cryo_notifier.packet()
        p.query_timers()
        result = yield p.send()
        rv = []
        for (name, t) in result['query_timers']:
            if self.cryo_name.lower() not in name.lower():
                continue

            t = int(t['s'])
            hours = t//3600
            minutes = (t - hours*3600)//60
            seconds = (t - hours*3600 - minutes*60)
            time_str = "%02d:%02d:%02d" % (hours, minutes, seconds)
            rv.append(tag.clone().fillSlots(name=name, time=time_str))
        returnValue(rv)

    @render_safe
    @inlineCallbacks
    def MKS(self, request, tag):
        p = self._cxn.mks_gauge_server_testhack.packet()
        p.get_gauge_list()
        p.get_readings()
        result = yield p.send()
        rv = []
        for (name, val) in zip(result['get_gauge_list'], result['get_readings']):
            rv.append(tag.clone().fillSlots(channel=name, pressure=str(val)))
        returnValue(rv)

    @render_safe
    @inlineCallbacks
    def logentries(self, request, tag):
        logdata = yield self.get_log()
        logdata = sorted(logdata, reverse=True)
        rv = [tag.clone().fillSlots(
                timestamp=tags.b("Fill Time"), 
                cryo_name=tags.b("Cryo"), 
                comments=tags.b("Comments"))]
        for entry in logdata:
            timestamp = entry[0]
            cryo_name = entry[1]
            if self.cryo_name.lower() not in cryo_name.lower():
                continue
            comments = entry[2]
            try: # convert to human readable date
                timestamp = datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f').ctime()
            except ValueError:
                pass
            rv.append(tag.clone().fillSlots(timestamp=timestamp, cryo_name=cryo_name, comments=tags.pre(comments)))
        returnValue(rv)


class RootStatusResource(Resource):
    '''
    The idea here is to have multiple status pages, each with their
    own Element subclass and .xml template, and have them automatically
    registered as subdirectories.  We would then provide a directory here
    browse.
    '''
    isLeaf=False
    def getChild(self, name, request):
        # Look to filesystem for an appropriately named module
        # Create a StatusPage with the Element from that module
        # and add it with putChild for direct lookup next time
        # 
        pass
    def render_GET(self, request):
        # Generate a directory of known status pages
        pass

class StatusResource(Resource):
    isLeaf=True
    def __init__(self, page_factory):
        self.factory = page_factory
        self.cxn = None
    def _delayedRender(self, request, data):
        request.write(data)
        request.finish()
    def set_cxn(self, cxn):
        self.cxn = cxn
    def render_GET(self, request):
        if self.cxn is None:
            return "Unable to connect to labrad.  Sorry"
        d = flattenString(None, self.factory(self.cxn, request))
        d.addCallback(lambda data: self._delayedRender(request, data))
        return NOT_DONE_YET

root = StatusResource(CryoStatusPage)

# The next bit here implements authentication  Uncomment it and set the username
# and password as you see fit to password protect the page.  However, a better
# approach is to us an Apache reverse-proxy and do authentication there.
'''
class LabRADHTMLRealm(object):
    implements(IRealm)
    def requestAvatar(self, avatarID, mind, *interfaces):
        if IResource in interfaces:
            return (IResource, root, lambda: None)
        raise NotImplementedError()

portal = Portal(LabRADHTMLRealm(), [pwdb(user='password')])
credentialFactory = DigestCredentialFactory("md5", "Labrad status pages")
authroot = HTTPAuthSessionWrapper(portal, [credentialFactory])

factory=Site(authroot)  
'''
factory = Site(root)

d = labrad.wrappers.connectAsync()
d.addCallback(root.set_cxn)
def cxn_failed(e):
    print "labrad connection failed: ", e
d.addErrback(cxn_failed)

reactor.listenTCP(8880, factory)
reactor.run()
