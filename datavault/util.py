import ConfigParser as cp

class DVSafeConfigParser(cp.SafeConfigParser):
    """.ini-style config parser with improved handling of line-endings.

    By default, SafeConfigParser uses the platform-default line ending, and
    does not allow specifying anything different. This version allows the
    line ending to be specified so that config files can be handled consistently
    across OSes.
    """

    def write(self, fp, newline='\r\n'):
        """Write an .ini-format representation of the configuration state."""
        if self._defaults:
            fp.write("[%s]" % cp.DEFAULTSECT + newline)
            for (key, value) in self._defaults.items():
                fp.write(("%s = %s" + newline) % (key, str(value).replace('\n', '\n\t')))
            fp.write(newline)
        for section in self._sections:
            fp.write("[%s]" % section + newline)
            for (key, value) in self._sections[section].items():
                if key != "__name__":
                    fp.write(("%s = %s" + newline) %
                             (key, str(value).replace('\n', '\n\t')))
            fp.write(newline)
