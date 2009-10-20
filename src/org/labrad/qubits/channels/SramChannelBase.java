package org.labrad.qubits.channels;

import java.util.Map;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModel;
import org.labrad.qubits.resources.DacBoard;

import com.google.common.collect.Maps;

public abstract class SramChannelBase<T> implements Channel {

  String name = null;
  Experiment expt = null;
  DacBoard board = null;
  FpgaModel fpga = null;

  @Override
  public String getName() {
    return name;
  }

  @Override
  public Experiment getExperiment() {
    return expt;
  }

  @Override
  public void setExperiment(Experiment expt) {
    this.expt = expt;
  }

  @Override
  public DacBoard getDacBoard() {
    return board;
  }

  public void setDacBoard(DacBoard board) {
    this.board = board;
  }

  @Override
  public FpgaModel getFpgaModel() {
    return fpga;
  }


  //
  // Blocks
  //

  Map<String, T> blocks = Maps.newHashMap();
}
