from __future__ import with_statement

import labrad

from GHz_DAC_bringup import checkBoard

raise Exception('Depricated. This module needs to be updated for the new style of DAC bringup. See fpga server documentation for details')

with labrad.connect() as cxn:
    fpga = cxn.ghz_fpgas
    boardList = [board for id, board in fpga.list_devices()]    
    resultList = [checkBoard(fpga, board, checkLock=True) for board in boardList]
    for board, result in zip(boardList, resultList):
        print '%s: %s' % (board, result)
        
print
raw_input('press <ENTER> to finish')
