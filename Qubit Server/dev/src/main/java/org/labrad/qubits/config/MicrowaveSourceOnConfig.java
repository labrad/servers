package org.labrad.qubits.config;

import org.labrad.data.Data;
import org.labrad.qubits.resources.MicrowaveSource;

public class MicrowaveSourceOnConfig implements MicrowaveSourceConfig {

  @Override
  public int hashCode() {
    final int prime = 31;
    int result = 1;
    long temp;
    temp = Double.doubleToLongBits(freq);
    result = prime * result + (int) (temp ^ (temp >>> 32));
    temp = Double.doubleToLongBits(power);
    result = prime * result + (int) (temp ^ (temp >>> 32));
    return result;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj)
      return true;
    if (obj == null)
      return false;
    if (getClass() != obj.getClass())
      return false;
    MicrowaveSourceOnConfig other = (MicrowaveSourceOnConfig) obj;
    if (Double.doubleToLongBits(freq) != Double
        .doubleToLongBits(other.freq))
      return false;
    if (Double.doubleToLongBits(power) != Double
        .doubleToLongBits(other.power))
      return false;
    return true;
  }

  private double freq;
  private double power;

  public MicrowaveSourceOnConfig(double freq, double power) {
    this.freq = freq;
    this.power = power;
  }

  @Override
  public double getFrequency() {
    return freq;
  }

  @Override
  public double getPower() {
    return power;
  }

  @Override
  public boolean isOn() {
    return true;
  }

  @Override
  public SetupPacket getSetupPacket(MicrowaveSource src) {
    Data data = Data.ofType("(ss)(sb)(sv[GHz])(sv[dBm])");
    data.get(0).setString("Select Device", 0).setString(src.getDevice(), 1);
    data.get(1).setString("Output", 0).setBool(true, 1);
    data.get(2).setString("Frequency", 0).setValue(freq, 1);
    data.get(3).setString("Amplitude", 0).setValue(power, 1);

    String state = String.format("%s: %g GHz @ %g dBm", src.getName(), freq, power);
    return new SetupPacket(state, data);
  }
}
