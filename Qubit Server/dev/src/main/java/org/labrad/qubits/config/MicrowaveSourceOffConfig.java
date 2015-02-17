package org.labrad.qubits.config;

import org.labrad.data.Data;
import org.labrad.qubits.resources.MicrowaveSource;


public class MicrowaveSourceOffConfig implements MicrowaveSourceConfig {

  @Override
  public double getFrequency() {
    return 6.0; // return a default frequency for the sake of deconvolution
    //throw new RuntimeException("Microwaves are off");
  }

  @Override
  public double getPower() {
    throw new RuntimeException("Microwaves are off");
  }

  @Override
  public boolean isOn() {
    return false;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj)
      return true;
    if (obj == null)
      return false;
    if (getClass() != obj.getClass())
      return false;
    return true;
  }

  @Override
  public SetupPacket getSetupPacket(MicrowaveSource src) {
    Data data = Data.ofType("(ss)(sb)");
    data.get(0).setString("Select Device", 0).setString(src.getDevice(), 1);
    data.get(1).setString("Output", 0).setBool(false, 1);

    String state = String.format("%s: off", src.getName());
    return new SetupPacket(state, data);
  }
}
