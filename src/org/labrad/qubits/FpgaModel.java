package org.labrad.qubits;

import java.util.List;
import java.util.concurrent.Future;

import org.labrad.qubits.channels.TriggerChannel;
import org.labrad.qubits.enums.DacTriggerId;
import org.labrad.qubits.mem.MemoryCommand;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.resources.DacBoard;

public interface FpgaModel {

  public String getName();
  public DacBoard getDacBoard();	

  //
  // SRAM
  //
  public void setTriggerChannel(DacTriggerId id, TriggerChannel ch);
  public Future<Void> deconvolveSram(DeconvolutionProxy deconvolver);

  //
  // Memory
  //
  public void clearMemory();
  public void addMemoryCommand(MemoryCommand cmd);
  public void addMemoryCommands(List<MemoryCommand> cmds);
  public void addMemoryNoop();
  public void addMemoryNoops(int n);
  public void addMemoryDelay(double microseconds);


  /**
   * Check whether the timer has been started at least once
   * @return
   */
  public boolean isTimerStarted();

  /**
   * Check whether the timer is currently running (has been started but not yet stopped)
   * @return
   */
  public boolean isTimerRunning();

  /**
   * Check whether the timer is currently started
   * @return
   */
  public boolean isTimerStopped();

  /**
   * Check that the timer status of this board is ok, namely that the timer
   * has been started at least once and stopped as many times as it has been
   * started.  This ensures that all boards will be run properly.
   */
  public void checkTimerStatus();

  public void startTimer();
  public void stopTimer();

  public void callSramBlock(String blockName);
  public void callSramDualBlock(String block1, String block2);
  public void setSramDualBlockDelay(double delay);
  public boolean hasDualBlockSram();

  //
  // bit sequences
  //

  /**
   * Get the bits of the memory sequence for this board
   */
  public long[] getMemory();

  /**
   * Get the bits for the SRAM sequence for this board
   * @return
   */
  public long[] getSram();

  /**
   * Get bits for the first block of a dual-block SRAM call
   * @return
   */
  public long[] getSramDualBlock1();

  /**
   * Get bits for the second block of a dual-block SRAM call
   * @return
   */
  public long[] getSramDualBlock2();

  /**
   * Get the delay between blocks in a dual-block SRAM call
   * @return
   */
  public long getSramDualBlockDelay();
}
