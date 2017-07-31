#!/usr/bin/python
from __future__ import division

from twisted.web.template import flattenString, Element, renderer, XMLFile
from twisted.python.filepath import FilePath

class LabRADStatusPage(Element):
    loader = XMLFile('cryo_log.xml')

    @renderer
    def name(self, request, tag):
        return tag("Vince")

    @renderer
    def logentries(self, request, tag):
        return tag("")

def renderDone(output):
    print output

flattenString(None, LabRADStatusPage()).addCallback(renderDone)
