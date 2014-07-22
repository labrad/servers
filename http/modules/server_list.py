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
    def get_log(self):
        p = self._cxn.registry.packet()
        p.cd(self.white_list_path)
        p.dir()
        p.cd([''])
        rv = yield p.send()
        subdirs, keys = rv['dir']
        keys = sorted(keys, reverse=True)[:self.max_entries]
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
    def maxentries(self, request, tag):
        if self.max_entries:
            return tag(str(self.max_entries))
        else:
            return tag("Unknown")

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
            rv.append(tag.clone().fillSlots(channel="%d: " % (idx+1,), temp="%.3f %s" % (val, unit_str)))
        returnValue(rv)
       

    @render_safe
    @inlineCallbacks
    def RuOx(self, request, tag):
        server = self._cxn.lakeshore_ruox
        p  = server.packet()
        p.select_device()
        p.named_temperatures()
        result = yield p.send()
        rv = []
        for idx, (name, (temp, dt)) in enumerate(result['named_temperatures']):
            val = temp['K']
            if val<1:
                val = val*1000
                unit_str = 'mK'
            else:
                unit_str = 'K'
            rv.append(tag.clone().fillSlots(channel="%s: " % (name,), temp="%.3f %s" % (val, unit_str)))
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
            if hours < 1:
                time_str = tags.font(time_str, color="#FF0000")
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
        
    @render_safe
    @inlineCallbacks
    def serverentries(self, request, tag):
        serverdata = yield self.get_all_servers()
        rv = [tag.clone().fillSlots(servername=tags.b("Server"))]
        for entry in serverdata:
            servername = entry
            rv.append(tag.clone().fillSlots(servername=servername))
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
