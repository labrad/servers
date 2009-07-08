"""
## wiring configuration

from registry ['', 'Servers', 'Wiring']
resources: *(s{type} s{name})
fibers: *((s{dacboard} s{fiber}) (s{cardname} s{channel}))
microwaves: *(s{dacboard} s{anritsudevice})

FPGA boards: - board groups, daisy chain order, delays
- info about which board group is connected to which ethernet port (stored in ghz_dac registry entry)

DC Rack: - rack groups, board types for different numbers.
- Possibly want to store zero calibration data for different channels?
- info about which rack is connected to which serial port (stored in dc_rack registry entry)





## experiment configuration

experiment = (<name>, cluster of <devices>)
device = (<name>, <type>, cluster of <channels>)
channel = (<name>, <type>, cluster of <params>)

AnalogChannel params = (<board name>, <dac id>)
IqChannel params = (<board name>)
TriggerChannel params = (<board name>, <trig id>)
FastBiasChannel params = (<card name>, <dac id>)
PreampChannel params = (<card name>, <dac id>)

experiment = (
    'single qubit', [
        ('q0', 'qubit', [
            ('meas', 'AnalogChannel', ('DR Lab FPGA 1', 'A')),
            ('uwave', 'IqChannel', ('DR Lab FPGA 2')),
        ]),
    ])
"""