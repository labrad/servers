package org.labrad.qubits.channels;

import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.FpgaModelDac;
import org.labrad.qubits.channeldata.TriggerData;
import org.labrad.qubits.channeldata.TriggerDataTime;
import org.labrad.qubits.enums.DacTriggerId;
import org.labrad.qubits.resources.DacBoard;

import com.google.common.base.Preconditions;

public class TriggerChannel extends SramChannelBase<TriggerData> {

  DacTriggerId triggerId = null;

  public TriggerChannel(String name) {
    this.name = name;
  }

  @Override
  public void setFpgaModel(FpgaModel fpga) {
    Preconditions.checkArgument(fpga instanceof FpgaModelDac,
        "TriggerChannel '%s' requires FpgaModelDac.", getName());
    this.fpga = (FpgaModelDac) fpga;
    this.fpga.setTriggerChannel(triggerId, this);
  }

  public void setDacBoard(DacBoard board) {
    this.board = board;
  }

  public void setTriggerId(DacTriggerId id) {
    triggerId = id;
  }

  public int getShift() {
    return triggerId.getShift();
  }

  public DacBoard getDacBoard() {
    return board;
  }

  public DacTriggerId getTriggerId() {
    return triggerId;
  }

  public void addData(TriggerData data) {
    int expected = fpga.getBlockLength(currentBlock);
    data.checkLength(expected);
    blocks.put(currentBlock, data);
  }

  public void addPulse(int start, int len) {
    boolean[] data = getSramData(currentBlock);
    start = Math.max(0, start);
    int end = Math.min(data.length, start + len);
    for (int i = start; i < end; i++) {
      data[i] = true;
    }
  }

  public boolean[] getSramData(String name) {
    TriggerData d = blocks.get(name);
    if (d == null) {
      // create a dummy data block
      int length = fpga.getBlockLength(name);
      boolean[] zeros = new boolean[length];
      d = new TriggerDataTime(zeros);
      d.setChannel(this);
      blocks.put(name, d);
    }
    return d.get();
  }

  // configuration

  public void clearConfig() {
    // nothing to do here
  }
}
