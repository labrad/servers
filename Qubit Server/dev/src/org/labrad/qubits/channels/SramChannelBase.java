package org.labrad.qubits.channels;

import com.google.common.collect.Maps;
import org.labrad.data.Data;
import org.labrad.qubits.Experiment;
import org.labrad.qubits.FpgaModelDac;
import org.labrad.qubits.jumptable.JumpTable;
import org.labrad.qubits.resources.DacBoard;

import java.util.Map;

public abstract class SramChannelBase<T> implements SramChannel {

  String name = null;
  Experiment expt = null;
  DacBoard board = null;
  FpgaModelDac fpga = null;
  JumpTable jumpTable = null;

  public SramChannelBase() {
    jumpTable = new JumpTable();
  }

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
  
  // Start delay
	@Override
	public int getStartDelay() {
		return this.getFpgaModel().getStartDelay();
	}

	@Override
	public void setStartDelay(int startDelay) {
		this.getFpgaModel().setStartDelay(startDelay);
	}

  //
  // Jump Table
  //
  public void clearJumpTable() {
    jumpTable.clear();
  }
  public void addJumpTableEntry(String name, Data data) {
    jumpTable.addEntry(name, data);
  }
  public void setCounters(long[] counters) {
    jumpTable.setCounters(counters);
  }


  public JumpTable getJumpTable() {
    return jumpTable;
  }
}
