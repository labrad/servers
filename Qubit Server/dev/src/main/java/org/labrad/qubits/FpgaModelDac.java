package org.labrad.qubits;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Future;
import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.qubits.channels.TriggerChannel;
import org.labrad.qubits.controller.FpgaController;
import org.labrad.qubits.controller.JumpTableController;
import org.labrad.qubits.controller.MemoryController;
import org.labrad.qubits.enums.DacTriggerId;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.resources.DacBoard;

/**
 * Responsible for managing the relation between a DAC's channels and its experiment, as well as producing
 * the actual packets to send to the FPGA server.
 * Control of the DAC (by memory commands or the jump table) is delegated to the controller member variable.
 */
public abstract class FpgaModelDac implements FpgaModel {

  public final static double FREQUENCY = 25.0;  // MHz
  public final static double DAC_FREQUENCY_MHz = 1000;
  public final static int MAX_MEM_LEN = 256; //words per derp
  public final static int START_DELAY_UNIT_NS = 4;
  private DacBoard dacBoard;
  protected Experiment expt;
  protected FpgaController controller;

  private final Map<DacTriggerId, TriggerChannel> triggers = Maps.newEnumMap(DacTriggerId.class);

  public FpgaModelDac(DacBoard dacBoard, Experiment expt) {
    this.dacBoard = dacBoard;
    this.expt = expt;
    // TODO: figure this out intelligently (from the build properties?)
    if (Integer.valueOf(dacBoard.getBuildNumber()) >= 13) {
      this.controller = new JumpTableController(this);
    } else {
      this.controller = new MemoryController(this);
    }
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

  public void addPackets(Request runRequest) {
    runRequest.add("Select Device", Data.valueOf(getName()));
    runRequest.add("Start Delay", Data.valueOf((long)getStartDelay()));
    controller.addPackets(runRequest);
    // TODO: having the dual block stuff here is a bit ugly
    if (controller.hasDualBlockSram()) {
      MemoryController memController = getMemoryController();
      runRequest.add("SRAM dual block",
              Data.valueOf(getSramDualBlock1()),
              Data.valueOf(getSramDualBlock2()),
              Data.valueOf(memController.getSramDualBlockDelay()));
    } else {
      runRequest.add("SRAM", Data.valueOf(getSram()));
    }
  }

  // Controller stuff
  public MemoryController getMemoryController() {
    try {
      return (MemoryController)controller;
    } catch (ClassCastException ex) {
      throw new RuntimeException("Cannot assign memory commands to jump table board " + getName());
    }
  }

  public JumpTableController getJumpTableController() {
    try {
      return (JumpTableController)controller;
    } catch (ClassCastException ex) {
      throw new RuntimeException("Cannot assign jump table commands to memory board " + getName());
    }
  }

  public void clearController() {
    controller.clear();
  }
  public double getSequenceLength_us() {
    return controller.getSequenceLength_us();
  }
  public double getSequenceLengthPostSRAM_us() {
    return controller.getSequenceLengthPostSRAM_us();
  }

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

  //
  // SRAM
  //

  public abstract Future<Void> deconvolveSram(DeconvolutionProxy deconvolver);

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
    MemoryController memoryController = getMemoryController();
    Preconditions.checkState(memoryController.hasDualBlockSram(), "Sequence does not have a dual-block SRAM call");
    if (!hasSramChannel()) {
      // return zeros in this case
      int len = Math.min(dacBoard.getBuildProperties().get("SRAM_LEN").intValue(), expt.getShortestSram());
      long[] sram = new long[len];
      Arrays.fill(sram, 0);
      return sram;
    } else {
      return getSramBlock(memoryController.getDualBlockName1());
    }
  }

  /**
   * Get bits for the second block of a dual-block SRAM call
   * @return
   */
  public long[] getSramDualBlock2() {
    MemoryController memoryController = getMemoryController();
    Preconditions.checkState(memoryController.hasDualBlockSram(), "Sequence does not have a dual-block SRAM call");
    if (!hasSramChannel()) {
      // return zeros in this case
      int len = Math.min(dacBoard.getBuildProperties().get("SRAM_LEN").intValue(), expt.getShortestSram());
      long[] sram = new long[len];
      Arrays.fill(sram, 0);
      return sram;
    } else {
      return getSramBlock(memoryController.getDualBlockName2(), false); // no autotrigger on second block
    }
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
    } else {
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

}
