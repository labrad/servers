# servers

A collection of LabRAD servers.  Many of these are for specific pieces of hardware.  In many only 
have the most basic functionality, or whatever the person who wrote them needed for their experiment.

Some servers that may be of general interest:

gpib_bus.py                 Provides an interface to a GPIB bus (uses VISA)
gpib_device_manager.py      Handles GPIB device identification and notifies the appropriate device server 
serial_server               Serial port interface using pyserial
data_vault.py               Store numeric data from experiments, supported by the grapher client
data_vault_multihead.py     Data vault implementation that can connect to multiple LabRAD managers

Some of the tools here require PyQt.
To install PyQt into a virtualenv in Linux, see [these instructions](https://docs.google.com/document/d/1PR0Xm6NqutMZs00Dt8U4CWlamVYgWxH52_8r-8apnVE/).

