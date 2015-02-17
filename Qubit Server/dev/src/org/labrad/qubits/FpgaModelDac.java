package org.labrad.qubits;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Future;

import org.labrad.data.Request;
import org.labrad.qubits.channels.TriggerChannel;
import org.labrad.qubits.enums.DacTriggerId;
import org.labrad.qubits.mem.CallSramCommand;
import org.labrad.qubits.mem.CallSramDualBlockCommand;
import org.labrad.qubits.mem.DelayCommand;
import org.labrad.qubits.mem.EndSequenceCommand;
import org.labrad.qubits.mem.MemoryCommand;
import org.labrad.qubits.mem.NoopCommand;
import org.labrad.qubits.mem.StartTimerCommand;
import org.labrad.qubits.mem.StopTimerCommand;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.resources.DacBoard;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;

public abstract class FpgaModelDac implements FpgaModel {

  public final static double FREQUENCY = 25.0;  // MHz
  public final static double DAC_FREQUENCY_MHz = 1000;
  public final static int MAX_MEM_LEN = 256; //words per derp
  public final static int START_DELAY_UNIT_NS = 4;
  private DacBoard dacBoard;
  protected Experiment expt;

  private final Map<DacTriggerId, TriggerChannel> triggers = Maps.newEnumMap(DacTriggerId.class);

  public FpgaModelDac(DacBoard dacBoard, Experiment expt) {
    this.dacBoard = dacBoard;
    this.expt = expt;
    clearMemory();
  }

  public String getName() {
    return dacBoard.getName();
  }

  public DacBoard getDacBoard() {
    return dacBoard;
  }
  
  // This method is needed by the memory SRAM commands to compute their own length.
  public Experiment getExperiment() {
	  return expt;
  }
  //
  // Start Delay - pomalley 5/4/2011
  //
  private int startDelay = 0;
  public void setStartDelay(int startDelay) {
	  this.startDelay = startDelay;
  }
  public int getStartDelay() {
	  return this.startDelay;
  }

  //
  // Wiring
  //

  public void setTriggerChannel(DacTriggerId id, TriggerChannel ch) {
    triggers.put(id, ch);
  }


  //
  // Memory
  //

  private final List<MemoryCommand> memory = Lists.newArrayList();
  private int timerStartCount = 0;
  private int timerStopCount = 0;
  private boolean sramCalled = false;
  private boolean sramCalledDualBlock = false;
  private CallSramDualBlockCommand sramDualBlockCmd = null;
  private Double sramDualBlockDelay = null;

  public void clearMemory() {
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
    int cycles = (int)microsecondsToClocks(microseconds);
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
	  double t_us=this.startDelay * START_DELAY_UNIT_NS / 1000.0;
	  for (MemoryCommand mem_cmd : this.memory) {
		  t_us += mem_cmd.getTime_us(this);
	  }
	  return t_us;
  }
  @Override
  public double getSequenceLengthPostSRAM_us() {
	  double t_us=this.startDelay * START_DELAY_UNIT_NS / 1000.0;
	  boolean SRAMStarted = false;
	  for (MemoryCommand mem_cmd : this.memory) {
		  if ( (mem_cmd instanceof CallSramDualBlockCommand) || (mem_cmd instanceof CallSramCommand)) {
			  SRAMStarted = true;
		  }
		  if (SRAMStarted) {
			  t_us += mem_cmd.getTime_us(this);
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
    Preconditions.checkState(isTimerStarted(), "%s: timer not started", getName());
    Preconditions.checkState(isTimerStopped(), "%s: timer not stopped", getName());
  }

  /**
   * Issue a start timer command.  Will only succeed if the timer is currently stopped.
   */
  public void startTimer() {
    Preconditions.checkState(isTimerStopped(), "%s: timer already started", getName());
    addMemoryCommand(StartTimerCommand.getInstance());
    timerStartCount++;
  }

  /**
   * Issue a stop timer command.  Will only succeed if the timer is currently running.
   */
  public void stopTimer() {
    Preconditions.checkState(isTimerRunning(), "%s: timer not started", getName());
    addMemoryCommand(StopTimerCommand.getInstance());
    timerStopCount++;
  }

  // Timing Data Conversions
  
  public static double clocksToMicroseconds(long cycles) {
    return cycles / FREQUENCY;
  }
  
  public static double[] clocksToMicroseconds(long[] cycles) {
    double[] ans = new double[cycles.length];
    for (int i = 0; i < cycles.length; i++) {
      ans[i] = clocksToMicroseconds(cycles[i]);
    }
    return ans;
  }
  
  public static long microsecondsToClocks(double microseconds) {
    return (long)(microseconds * FREQUENCY);
  }
  
  public double samplesToMicroseconds(long s) {
	  return s / DAC_FREQUENCY_MHz;
  }

  // SRAM calls

  //
  // SRAM
  //
  public abstract Future<Void> deconvolveSram(DeconvolutionProxy deconvolver);
  
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

  public boolean hasDualBlockSram() {
    return sramCalledDualBlock;
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
        if (getBlockNames().contains(block)) {
        	cmd.setStartAddress(this.getBlockStartAddress(block));
        	cmd.setEndAddress(this.getBlockEndAddress(block));
        } else {
        	// if this block wasn't defined for us, then it will be filled with zeros
        	cmd.setStartAddress(0);
        	cmd.setEndAddress(expt.getShortestSram());
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
    if (bits.length > this.dacBoard.getBuildProperties().get("SRAM_WRITE_PKT_LEN")) {
      throw new RuntimeException("Memory sequence exceeds maximum length");
    }
    return bits;
  }

  /**
   * Get the bits for the full SRAM sequence for this board.
   * We loop over all called blocks, padding the bits from each block
   * and then concatenating them together.
   * 
   * pomalley 4/22/2014 -- Added check for hasSramChannel(), and in the
   * case where it is false, just do zeroes of the whole memory length.
   * See comment on hasSramChannel.
   * @return
   */
  public long[] getSram() {
    long[] sram;
    if (hasSramChannel()) {
      // get bits for all SRAM blocks
      int len = 0;
      List<long[]> blocks = Lists.newArrayList();
      for (String blockName : this.getBlockNames()) {
        long[] block = getSramBlock(blockName);
        padArrayFront(block, this.getPaddedBlockLength(blockName));
        blocks.add(block);
        len += block.length;
      }
      // concatenate blocks into one array
      sram = new long[len];
      // the length of long[sram] is effectively set by the experiment. it may be longer than the SRAM of this board.
      // but if we aren't using this board and are just filling its SRAM with zeroes, that may be unnecessary.
      int pos = 0;
      for (long[] block : blocks) {
        System.arraycopy(block, 0, sram, pos, block.length);
        pos += block.length;
      }
    } else {
      int len = dacBoard.getBuildProperties().get("SRAM_LEN").intValue();
      if (expt.getShortestSram() < len) {
        //System.out.println(getName() + ": len: " + len + ", shortest: " + expt.getShortestSram());
        len = expt.getShortestSram();
      }
      sram = new long[len];
      Arrays.fill(sram, 0);
    }
    // check that the total sram sequence is not too long
    if (sram.length > this.dacBoard.getBuildProperties().get("SRAM_LEN")) {
      throw new RuntimeException("SRAM sequence exceeds maximum length. Length = " + sram.length + "; allowed = " +
      		this.dacBoard.getBuildProperties().get("SRAM_LEN") + "; for board " + getName());
    }
    return sram;
  }

  /**
   * Get bits for the first block of a dual-block SRAM call
   * @return
   */
  public long[] getSramDualBlock1() {
    Preconditions.checkState(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call");
    if (!hasSramChannel()) {
    	// return zeros in this case
    	int len = Math.min(dacBoard.getBuildProperties().get("SRAM_LEN").intValue(), expt.getShortestSram());
    	long[] sram = new long[len];
    	Arrays.fill(sram, 0);
    	return sram;
    } else {
    	return getSramBlock(sramDualBlockCmd.getBlockName1());
    }
  }

  /**
   * Get bits for the second block of a dual-block SRAM call
   * @return
   */
  public long[] getSramDualBlock2() {
    Preconditions.checkState(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call");
    if (!hasSramChannel()) {
    	// return zeros in this case
    	int len = Math.min(dacBoard.getBuildProperties().get("SRAM_LEN").intValue(), expt.getShortestSram());
    	long[] sram = new long[len];
    	Arrays.fill(sram, 0);
    	return sram;
    } else {
    	return getSramBlock(sramDualBlockCmd.getBlockName2(), false); // no autotrigger on second block
    }
  }

  /**
   * Get the delay between blocks in a dual-block SRAM call
   * @return
   */
  public long getSramDualBlockDelay() {
    Preconditions.checkState(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call");
    return (long)sramDualBlockCmd.getDelay();
  }

  /**
   * Get the SRAM bits for a particular block.
   * @param block
   * @return
   */
  private long[] getSramBlock(String block) {
    return getSramBlock(block, true);
  }

  /**
   * Get the SRAM bits for a particular block.
   * @param block
   * @return
   */
  private long[] getSramBlock(String block, boolean addAutoTrigger) {
    long[] sram = getSramDacBits(block);
    setTriggerBits(sram, block, addAutoTrigger);
    return sram;
  }

  /**
   * Get DAC sram bits for a particular block.  This is
   * implemented differently for different board configurations
   * (analog vs. microwave) so it is deferred to concrete subclasses.
   * @param block
   * @return
   */
  protected abstract long[] getSramDacBits(String block);
  
  /**
   * pomalley 4/22/14
   * This fpga may not have an SRAM channel if we are only using this board for FastBias control.
   * In this case, since the SRAM will be only zeroes, we won't send a sequence
   * as long as all the blocks in the Experiment object, since that may be
   * longer than the SRAM of the boards. We will only send one as long as the memory
   * of the boards.
   * @return Whether or not we have an SRAM channel (IQ or analog) for this board.
   */
  protected abstract boolean hasSramChannel();

  /**
   * Set trigger bits in an array of DAC bits.
   * @param s
   * @param block
   */
  private void setTriggerBits(long[] s, String block, boolean addAutoTrigger) {
    DacTriggerId autoTriggerId = expt.getAutoTriggerId();
    boolean foundAutoTrigger = false;
    
    for (TriggerChannel ch : triggers.values()) {
      boolean[] trigs = ch.getSramData(block);
      if (addAutoTrigger && (expt.getAutoTriggerId() == ch.getTriggerId())) {
        foundAutoTrigger = true;
        for (int i = 4; i < 4 + expt.getAutoTriggerLen(); i++) {
          if (i < trigs.length - 1) trigs[i] = true;
        }
      }
      long bit = 1L << ch.getShift();
      for (int i = 0; i < s.length; i++) {
        s[i] |= trigs[i] ? bit : 0;
      }
    }
    
    // set autotrigger bits even if there is no defined trigger channel
    // TODO define dummy trigger channels, just like we do with Microwave and analog channels
    if (!foundAutoTrigger && autoTriggerId != null) {
      long bit = 1L << autoTriggerId.getShift();
      for (int i = 4; i < 4 + expt.getAutoTriggerLen(); i++) {
        if (i < s.length - 1) s[i] |= bit;
      }
    }
  }

  /**
   * Pad an array to the given length by repeating the first value the specified number of times
   * @param data
   * @param len
   * @return
   */
  protected long[] padArrayFront(long[] data, int len) {
    if (len <= data.length) return data;
    long[] newData = new long[len];
    int padding = len - data.length;
    Arrays.fill(newData, 0, padding - 1, data[0]); // repeat first value at the beginning
    System.arraycopy(data, 0, newData, padding, data.length); // copy the rest
    return newData;
  }

  /**
   * Pad an array to the given length by repeating the first value the specified number of times
   * @param data
   * @param len
   * @return
   */
  protected long[] padArrayBack(long[] data, int len) {
    if (len <= data.length) return data;
    long[] newData = new long[len];
    long last = data[data.length-1];
    System.arraycopy(data, 0, newData, 0, data.length); // copy at the beginning
    Arrays.fill(newData, data.length, newData.length - 1, last); // repeat last value
    return newData;
  }
  

  //
  // SRAM block management
  //

  private List<String> blocks = Lists.newArrayList();
  private Map<String, Integer> blockLengths = Maps.newHashMap();

  public void startSramBlock(String name, long length) {
	  if (blocks.contains(name)) {
		  Preconditions.checkArgument(blockLengths.get(name) == length,
				  "Conflicting block lengths for block '" + name + "' for FPGA " + getName() + " (DAC board " + dacBoard.getName() + ")");
	  }  else {
		  blocks.add(name);
		  blockLengths.put(name, (int)length);
	  }
  }

  public List<String> getBlockNames() {
    return Lists.newArrayList(blocks);
  }

  public int getBlockLength(String name) {
    Preconditions.checkArgument(blockLengths.containsKey(name), "SRAM block '%s' is undefined for board %s", name, getName());
    return blockLengths.get(name);
  }

  /**
   * Get the proper length for an SRAM block after padding.
   * The length should be a multiple of 4 and greater or equal to 20.
   * @param name
   * @return
   */
  public int getPaddedBlockLength(String name) {
    int len = getBlockLength(name);
    if (len % 4 == 0 && len >= 20) return len;
    int paddedLen = Math.max(len + ((4 - len % 4) % 4), 20);
    return paddedLen;
  }

  public int getBlockStartAddress(String name) {
    int start = 0;
    for (String block : blocks) {
      if (block.equals(name)) {
        return start;
      }
      start += getPaddedBlockLength(block);
    }
    throw new RuntimeException(String.format("Block '%s' not found", name));
  }

  public int getBlockEndAddress(String name) {
    int end = 0;
    for (String block : blocks) {
      end += getPaddedBlockLength(block);
      if (block.equals(name)) {
        return end - 1; //Zero indexing ;)
      }
    }
    throw new RuntimeException(String.format("Block '%s' not found", name));
  }

  public abstract void addJumpTablePackets(Request runRequest);
  public abstract void clearJumpTable();
}
