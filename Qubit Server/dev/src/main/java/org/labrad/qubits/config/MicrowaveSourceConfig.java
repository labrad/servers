package org.labrad.qubits.config;

import org.labrad.qubits.resources.MicrowaveSource;

public interface MicrowaveSourceConfig {
  public boolean isOn();
  public double getFrequency();
  public double getPower();

  public SetupPacket getSetupPacket(MicrowaveSource src);
}
