import os
import sys

import labrad
import labrad.util

def main(args):
    """Configure the data directory for the local labrad node."""
    directory = os.path.abspath(args[1])

    node = labrad.util.getNodeName()

    print "Configuring data vault repository for node '{}' to {}".format(node, directory)
    assert os.path.exists(directory)
    assert os.path.isdir(directory)

    with labrad.connect() as cxn:
        reg = cxn.registry()
        reg.cd(['', 'Servers', 'Data Vault', 'Repository'], True)
        reg.set(node, directory)

if __name__ == '__main__':
    main(sys.argv)
