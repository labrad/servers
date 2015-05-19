package org.labrad.qubits.controller;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;
import org.labrad.data.Data;
import org.labrad.data.Record;
import org.labrad.data.Request;
import org.labrad.qubits.FpgaModelDac;
import org.labrad.qubits.mem.*;

import java.util.List;

/**
 * The MemoryController
 */
public class MemoryController extends FpgaController {

  public MemoryController(FpgaModelDac fpgaModelDac) {
    super(fpgaModelDac);
    clear();
  }

  private final List<MemoryCommand> memory = Lists.newArrayList();
  private int timerStartCount = 0;
  private int timerStopCount = 0;
  private boolean sramCalled = false;
  private boolean sramCalledDualBlock = false;
  private CallSramDualBlockCommand sramDualBlockCmd = null;
  private Double sramDualBlockDelay = null;

  public void addPackets(Request runRequest) {
    runRequest.add("Memory", Data.valueOf(getMemory()));
  }

  public void clear() {
    memory.clear();
    timerStartCount = 0;
    timerStopCount = 0;
    sramCalled = false;
    sramCalledDualBlock = false;
    sramDualBlockCmd = null;
  }

  public void addMemoryCommand(MemoryCommand cmd) {
    memory.add(cmd);
  }

  public void addMemoryCommands(List<MemoryCommand> cmds) {
    memory.addAll(cmds);
  }

  public void addMemoryNoop() {
    addMemoryCommand(NoopCommand.getInstance());
  }

  public void addMemoryNoops(int n) {
    for (int i = 0; i < n; i++) {
      addMemoryCommand(NoopCommand.getInstance());
    }
  }

  public void addMemoryDelay(double microseconds) {
    int cycles = (int) FpgaModelDac.microsecondsToClocks(microseconds);
    int mem_size = this.memory.size();
    if (mem_size > 0) {
      MemoryCommand last_cmd = this.memory.get(this.memory.size()-1);
      if (last_cmd instanceof DelayCommand) {
        DelayCommand delay_cmd = (DelayCommand) last_cmd;
        delay_cmd.setDelay(cycles + delay_cmd.getDelay());
      } else {
        addMemoryCommand(new DelayCommand(cycles));
      }
    } else {
      addMemoryCommand(new DelayCommand(cycles));
    }
  }



  @Override
  public double getSequenceLength_us() {
    double t_us = this.fpga.getStartDelay() * FpgaModelDac.START_DELAY_UNIT_NS / 1000.0;
    for (MemoryCommand mem_cmd : this.memory) {
      t_us += mem_cmd.getTime_us(fpga);
    }
    return t_us;
  }
  @Override
  public double getSequenceLengthPostSRAM_us() {
    double t_us=this.fpga.getStartDelay() * FpgaModelDac.START_DELAY_UNIT_NS / 1000.0;
    boolean SRAMStarted = false;
    for (MemoryCommand mem_cmd : this.memory) {
      if ( (mem_cmd instanceof CallSramDualBlockCommand) || (mem_cmd instanceof CallSramCommand)) {
        SRAMStarted = true;
      }
      if (SRAMStarted) {
        t_us += mem_cmd.getTime_us(fpga);
      }
    }
    return t_us;
  }
  // timer logic

  /**
   * Check whether the timer has been started at least once
   * @return
   */
  public boolean isTimerStarted() {
    return timerStartCount > 0;
  }

  /**
   * Check whether the timer is currently running (has been started but not yet stopped)
   * @return
   */
  public boolean isTimerRunning() {
    return timerStartCount == timerStopCount + 1;
  }

  /**
   * Check whether the timer is currently stopped
   * @return
   */
  public boolean isTimerStopped() {
    return timerStartCount == timerStopCount;
  }

  /**
   * Check that the timer status of this board is ok, namely that the timer
   * has been started at least once and stopped as many times as it has been
   * started.  This ensures that all boards will be run properly.
   */
  public void checkTimerStatus() {
    Preconditions.checkState(isTimerStarted(), "%s: timer not started", fpga.getName());
    Preconditions.checkState(isTimerStopped(), "%s: timer not stopped", fpga.getName());
  }

  /**
   * Issue a start timer command.  Will only succeed if the timer is currently stopped.
   */
  public void startTimer() {
    Preconditions.checkState(isTimerStopped(), "%s: timer already started", fpga.getName());
    addMemoryCommand(StartTimerCommand.getInstance());
    timerStartCount++;
  }

  /**
   * Issue a stop timer command.  Will only succeed if the timer is currently running.
   */
  public void stopTimer() {
    Preconditions.checkState(isTimerRunning(), "%s: timer not started", fpga.getName());
    addMemoryCommand(StopTimerCommand.getInstance());
    timerStopCount++;
  }

  // SRAM calls

  //
  // SRAM
  //

  public void callSramBlock(String blockName) {
    Preconditions.checkState(!sramCalledDualBlock, "Cannot call SRAM and dual-block in the same sequence.");
    addMemoryCommand(new CallSramCommand(blockName));
    sramCalled = true;
  }

  public void callSramDualBlock(String block1, String block2) {
    Preconditions.checkState(!sramCalled, "Cannot call SRAM and dual-block in the same sequence.");
    Preconditions.checkState(!sramCalledDualBlock, "Only one dual-block SRAM call allowed per sequence.");
    CallSramDualBlockCommand cmd = new CallSramDualBlockCommand(block1, block2, sramDualBlockDelay);
    addMemoryCommand(cmd);
    sramDualBlockCmd = cmd;
    sramCalledDualBlock = true;
  }

  public void setSramDualBlockDelay(double delay_ns) {
    sramDualBlockDelay = delay_ns;
    if (sramCalledDualBlock) {
      // need to update the already-created dual-block command
      sramDualBlockCmd.setDelay(delay_ns);
    }
  }

  @Override
  public boolean hasDualBlockSram() {
    return sramCalledDualBlock;
  }

  /**
   * Get the delay between blocks in a dual-block SRAM call
   * @return
   */
  public long getSramDualBlockDelay() {
    Preconditions.checkState(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call");
    return (long)sramDualBlockCmd.getDelay();
  }



  //
  // bit sequences
  //

  /**
   * Get the bits of the memory sequence for this board
   */
  public long[] getMemory() {
    List<MemoryCommand> mem = Lists.newArrayList(memory);
    // add initial noop and final mem commands
    mem.add(0, NoopCommand.getInstance());
    mem.add(EndSequenceCommand.getInstance());

    // resolve addresses of all SRAM blocks
    for (MemoryCommand c : mem) {
      if (c instanceof CallSramCommand) {
        CallSramCommand cmd = (CallSramCommand)c;
        String block = cmd.getBlockName();
        if (fpga.getBlockNames().contains(block)) {
          cmd.setStartAddress(fpga.getBlockStartAddress(block));
          cmd.setEndAddress(fpga.getBlockEndAddress(block));
        } else {
          // if this block wasn't defined for us, then it will be filled with zeros
          cmd.setStartAddress(0);
          cmd.setEndAddress(fpga.getExperiment().getShortestSram());
        }
      }
    }

    // get bits for all memory commands
    int len = 0;
    List<long[]> memBits = Lists.newArrayList();
    for (MemoryCommand cmd : mem) {
      long[] bits = cmd.getBits();
      memBits.add(bits);
      len += bits.length;
    }
    // concatenate commands into one array
    long[] bits = new long[len];
    int pos = 0;
    for (long[] cmdBits : memBits) {
      System.arraycopy(cmdBits, 0, bits, pos, cmdBits.length);
      pos += cmdBits.length;
    }

    // check that the total memory sequence is not too long
    if (bits.length > fpga.getDacBoard().getBuildProperties().get("SRAM_WRITE_PKT_LEN")) {
      throw new RuntimeException("Memory sequence exceeds maximum length");
    }
    return bits;
  }

  public String getDualBlockName1() {
    Preconditions.checkState(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call");
    return sramDualBlockCmd.getBlockName1();
  }

  public String getDualBlockName2() {
    Preconditions.checkState(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call");
    return sramDualBlockCmd.getBlockName2();
  }
}
