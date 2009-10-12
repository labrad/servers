"""
## wiring configuration

from registry ['', 'Servers', 'Qubit Server', 'Wiring']
resources: *(s{type} s{name})
fibers: *((s{dacboard} s{fiber}) (s{cardname} s{channel}))
microwaves: *(s{dacboard} s{anritsudevice})

FPGA boards: - board groups, daisy chain order, delays
- info about which board group is connected to which ethernet port (stored in ghz_dac registry entry)
- need to have the ghz dac server hot reload configuration changes (also, have a configuration editor)

DC Rack: - rack groups, board types for different numbers.
- Possibly want to store zero calibration data for different channels?
- info about which rack is connected to which serial port (stored in dc_rack registry entry)





## experiment configuration

experiment = [<device>,...]
device = (<name>, [<channel>,...])
channel = (<name>, (<type>, [<param>,...]))

AnalogChannel params = [<board name>, <dac id>]
IqChannel params = [<board name>]
TriggerChannel params = [<board name>, <trig id>]
FastBiasChannel params = [<card name>, <dac id>]
PreampChannel params = [<card name>, <dac id>]

python:
experiment = [
    ('q0', [
        ('meas', ('AnalogChannel', ['DR Lab FPGA 1', 'A'])),
        ('uwave', ('IqChannel', ['DR Lab FPGA 2'])),
    ]),
    ('q1', [
        ('meas', ('AnalogChannel', ['DR Lab FPGA 1', 'B'])),
        ('uwave', ('IqChannel', ['DR Lab FPGA 3'])),
    ]),
]
    
registry:
path/
    q0/
        meas: ('AnalogChannel', ['DR Lab FPGA 1', 'A'])
        uwave: ('IqChannel', ['DR Lab FPGA 2'])
    q1/
        meas: ('AnalogChannel', ['DR Lab FPGA 1', 'B'])
        uwave: ('IqChannel', ['DR Lab FPGA 3'])
"""


