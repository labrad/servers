package org.labrad.qubits.channels;

import java.util.Map;

import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModelDac;
import org.labrad.qubits.resources.DacBoard;

import com.google.common.collect.Maps;

public abstract class SramChannelBase<T> implements Channel {

  String name = null;
  Experiment expt = null;
  DacBoard board = null;
  FpgaModelDac fpga = null;

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
  public FpgaModelDac getFpgaModel() {
    return fpga;
  }


  //
  // Blocks
  //
  protected String currentBlock;
  public String getCurrentBlock() {
	  return currentBlock;
  }
  public void setCurrentBlock(String block) {
	  currentBlock = block;
  }

  Map<String, T> blocks = Maps.newHashMap();
}
