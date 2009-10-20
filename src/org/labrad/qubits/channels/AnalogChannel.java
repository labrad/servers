package org.labrad.qubits.channels;

import java.util.Arrays;

import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.FpgaModelAnalog;
import org.labrad.qubits.channeldata.AnalogData;
import org.labrad.qubits.channeldata.AnalogDataFourier;
import org.labrad.qubits.enums.DacAnalogId;
import org.labrad.qubits.util.ComplexArray;

import com.google.common.base.Preconditions;

public class AnalogChannel extends SramChannelBase<AnalogData> {

  DacAnalogId dacId = null;

  public AnalogChannel(String name) {
    this.name = name;
    clearConfig();
  }

  public void setDacId(DacAnalogId id) {
    dacId = id;
  }

  public DacAnalogId getDacId() {
    return dacId;
  }

  @Override
  public void setFpgaModel(FpgaModel fpga) {
    Preconditions.checkArgument(fpga instanceof FpgaModelAnalog,
        "AnalogChannel '%s' requires analog board.", getName());
    FpgaModelAnalog fpgaAnalog = (FpgaModelAnalog)fpga;
    this.fpga = fpgaAnalog;
    fpgaAnalog.setAnalogChannel(dacId, this);
  }

  public void addData(String block, AnalogData data) {
    int expected = expt.getBlockLength(block);
    data.setChannel(this);
    data.checkLength(expected);
    blocks.put(block, data);
  }

  public AnalogData getBlockData(String name) {
    AnalogData data = blocks.get(name);
    if (data == null) {
      // create a dummy data set with zeros
      int len = expt.getBlockLength(name);
      len = len % 2 == 0 ? len/2 + 1 : (len+1) / 2;
      double[] zeros = new double[len];
      data = new AnalogDataFourier(new ComplexArray(zeros, zeros), 0);
      data.setChannel(this);
      blocks.put(name, data);
    }
    return data;
  }

  public int[] getSramData(String name) {
    return blocks.get(name).getDeconvolved();
  }


  //
  // Configuration
  //

  double[] settlingRates, settlingAmplitudes;

  public void clearConfig() {
    settlingRates = new double[0];
    settlingAmplitudes = new double[0];
  }

  public void setSettling(double[] rates, double[] amplitudes) {
    Preconditions.checkArgument(rates.length == amplitudes.length,
        "%s: lists of settling rates and amplitudes must be the same length", getName());
    settlingRates = rates;
    settlingAmplitudes = amplitudes;
    // FIXME need to mark all blocks as needing deconvolution when config changes
  }

  public double[] getSettlingRates() {
    return Arrays.copyOf(settlingRates, settlingRates.length);
  }

  public double[] getSettlingTimes() {
    return Arrays.copyOf(settlingAmplitudes, settlingAmplitudes.length);
  }
}
