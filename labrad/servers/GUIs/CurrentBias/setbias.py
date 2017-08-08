from labrad.types import Value
from labrad.units import V, Hz, us


def volt2dac(voltage, channel):
    voltage = voltage['V']
    value = long(round((voltage + 2.5)/5.0 * 0xffff))
    if channel == 0:
        return 0x100000 + (((value & 0xffff) << 3) + 0x80000)
    elif channel == 1:
        return 0x200000 + (((value & 0xffff) << 3) + 0x80000)
    else:
        raise 'Wrong channel!'
        
        
def set_fb(dac, cxn, voltage, channel):
    mem = [0x000000L,
           volt2dac(voltage, channel),
           0x3009c4L,
           0x400000L,
           0x400001L,
           0xF00000L,]
    fpga = cxn.ghz_fpgas
    p = fpga.packet()
    p.select_device(dac)
    p.memory(mem)
    p.sram([0x00000L])
    p.send()
    daisyChainList = [dac]
    fpga.daisy_chain(daisyChainList)
    #fpga.timing_order([dac])
    result = fpga.run_sequence(1,False)
