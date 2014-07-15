package org.labrad.qubits.channeldata;


public class TriggerDataTime extends TriggerDataBase {

  private boolean[] vals;

  public TriggerDataTime(boolean[] vals) {
    this.vals = vals;
  }

  public void checkLength(int expected) {
    LengthChecker.checkLengths(vals.length, expected);
  }

  @Override
  public boolean[] get() {
    return vals;
  }
}
