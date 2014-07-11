package org.labrad.qubits.channels;

import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.FpgaModelMicrowave;
import org.labrad.qubits.channeldata.IqData;
import org.labrad.qubits.channeldata.IqDataFourier;
import org.labrad.qubits.config.MicrowaveSourceConfig;
import org.labrad.qubits.config.MicrowaveSourceOffConfig;
import org.labrad.qubits.config.MicrowaveSourceOnConfig;
import org.labrad.qubits.resources.MicrowaveSource;
import org.labrad.qubits.util.ComplexArray;

import com.google.common.base.Preconditions;

public class IqChannel extends SramChannelBase<IqData> {

  private MicrowaveSource uwaveSrc = null;
  private MicrowaveSourceConfig uwaveConfig;

  public IqChannel(String name) {
    this.name = name;
    clearConfig();
  }

  @Override
  public void setFpgaModel(FpgaModel fpga) {
    Preconditions.checkArgument(fpga instanceof FpgaModelMicrowave,
        "IqChannel '%s' requires microwave board.", getName());
    FpgaModelMicrowave fpgaMicrowave = (FpgaModelMicrowave)fpga; 
    this.fpga = fpgaMicrowave;
    fpgaMicrowave.setIqChannel(this);
  }

  public MicrowaveSource getMicrowaveSource() {
    return uwaveSrc;
  }

  public void setMicrowaveSource(MicrowaveSource src) {
    uwaveSrc = src;
  }

  /**
   * Add data to the current block
   * @param data
   */
  public void addData(IqData data) {
    int expected = fpga.getBlockLength(currentBlock);
    data.setChannel(this);
    data.checkLength(expected);
    blocks.put(currentBlock, data);
  }

  public IqData getBlockData(String name) {
    IqData data = blocks.get(name);
    if (data == null) {
      // create a dummy data set with zeros
      int expected = fpga.getBlockLength(name);
      double[] zeros = new double[expected];
      data = new IqDataFourier(new ComplexArray(zeros, zeros), 0);
      data.setChannel(this);
      blocks.put(name, data);
    }
    return data;
  }

  public int[] getSramDataA(String name) {
    return blocks.get(name).getDeconvolvedI();
  }

  public int[] getSramDataB(String name) {
    return blocks.get(name).getDeconvolvedQ();
  }

  // configuration

  public void clearConfig() {
    uwaveConfig = null;
  }

  public void configMicrowavesOn(double freq, double power) {
    uwaveConfig = new MicrowaveSourceOnConfig(freq, power);
    // mark all blocks as needing to be deconvolved again
    for (IqData block : blocks.values()) {
      block.invalidate();
    }
  }

  public void configMicrowavesOff() {
    uwaveConfig = new MicrowaveSourceOffConfig();
  }

  public MicrowaveSourceConfig getMicrowaveConfig() {
    Preconditions.checkNotNull(uwaveConfig, "No microwave configuration for channel '%s'", getName());
    return uwaveConfig;
  }

}
