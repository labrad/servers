package org.labrad.qubits.config;

import org.labrad.data.Data;

public class SetupPacket {
  private String state;
  private Data records;

  public SetupPacket(String state, Data records) {
    this.state = state;
    this.records = records;
  }

  public String getState() { return state; }
  public Data getRecords() { return records; }
}
