# servers

A collection of LabRAD servers.  Many of these are for specific pieces of hardware.  In many only 
have the most basic functionality, or whatever the person who wrote them needed for their experiment.

Some servers that may be of general interest:

gpib_bus.py                 Provides an interface to a GPIB bus (uses VISA)
gpib_device_manager.py      Handles GPIB device identification and notifies the appropriate device server 
serial_server               Serial port interface using pyserial
data_vault.py               Store numeric data from experiments, supported by the grapher client
data_vault_multihead.py     Data vault implementation that can connect to multiple LabRAD managers

## Set up environment

### Install PyQt and PyQwt in a virtualenv

We'd like to install PyQt and PyQwt into the virtualenv we use for labrad.
Unfortunately, as of this writing `pip install PyQt` doesn't work, so we need to do something else.
The following instructions will have you download the sources, compile them, and install into your virtualenv by invoking the python installation scripts manually with your virtualenv's interpreter.

1. Install requisite system libs for compiling PyQt: `sudo apt-get install python2.7-dev libxext-dev qt4-dev-tools build-essential`

1. Download the source packages for [SIP](https://www.riverbankcomputing.com/software/sip/download), [PyQt](https://www.riverbankcomputing.com/software/pyqt/download), and [PyQwt](http://pyqwt.sourceforge.net/).
Choose a location in which you will unpack the source packages.
In the following instructions we assume `~/src`.

1. Unpack the source packages
  1. `cd ~/src`
  1. `$ tar -zxf where/you/downloaded/sip-4.16.9.tar.gz`
  1. `$ tar -zxf where/you/downloaded/PyQt-x11-gpl-4.11.4.tar.gz`
  1. `$ tar -zxf where/you/downloaded/PyQwt-5.2.0.tar.gz`

1. Activate your virtualenv, e.g. via `workon myenv`.

1. Compile and install SIP
  1. If your virtualenv has symlinked the `~/.virtualenvs/myenv/include` directory, then we need to make our own space to put the SIP header file.
    1. `$ cd ~/.virtualenvs/myenv/include`
    1. `$ mkdir python2.7-pyqt`

  1. `$ cd ~/src/sip-4.16.9`
  1. `$ python configure.py --incdir=~/.virtualenvs/myenv/include/python2.7-pyqt`. If you skipped making the `python2.7-pyqt` directory, leave the `--incdir` flag off.
  1. `$ make`
  1. `$ sudo make install`
  1. You should see messages telling you that the relevant files are copied into your virtualenv.
  1. Check that each of the following files is owned by you, and if they're not, chown them to yourself:
    1. `~/.virtualenvs/myenv/bin/sip`
    1. `~/.virtualenvs/myenv/lib/python2.7/site-packages/sip.so`
    1. `~/.virtualenvs/myenv/lib/python2.7/site-packages/sipconfig.py`
    1. `~/.virtualenvs/myenv/lib/python2.7/site-packages/sipdistutils.py`
    1. `~/.virtualenvs/myenv/include/python2.7-pyqt/sip.h`. This only exists if you had to make the `python2.7-pyqt` directory.

1. Compile and install PyQt
  1. `$ cd ~/src/PyQt-x11-gpl-4.11.4`
  1. `$ python configure-ng.py -q /usr/bin/qmake-qt4 --sip-incdir=~/.virtualenvs/myenv/include/python2.7-pyqt`. Again, if you didn't need the step where you made the `python2.7-pyqt` directory, leave off the `--sip-incdir` flag.
  1. `$ make -j4` # This step might take a while.
  1. `$ sudo make install`

1. Compile and install PyQwt
  1. `$ cd ~/src/PyQwt-5.2.0/configure`
  1. `$ python configure.py -Q ../qwt-5.2`
  1. `$ make -j4`
  1. `$ sudo make install`
