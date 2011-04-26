package org.labrad.qubits;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.labrad.data.Data;
import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.channels.PreampChannel;
import org.labrad.qubits.channels.TimingChannel;
import org.labrad.qubits.enums.DacTriggerId;
import org.labrad.qubits.mem.MemoryCommand;
import org.labrad.qubits.resources.AdcBoard;
import org.labrad.qubits.resources.AnalogBoard;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.resources.MicrowaveBoard;

import com.google.common.base.Preconditions;
import com.google.common.collect.ListMultimap;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;
import com.google.common.collect.Sets;


/**
 * "Experiment holds all the information about the fpga sequence as it is being built,
 * and knows how to produce the memory and sram instructions that actually get sent out to run the sequence."
 * 
 * For the ADC addition, we now have to be careful to only perform things like memory ops on DAC FpgaModels, not ADC ones.
 * 
 * @author maffoo
 * @author pomalley
 */
public class Experiment {

  /**
   * Create a new experiment using the given list of devices.
   * @param devices
   */
  public Experiment(List<Device> devices) {
    for (Device dev : devices) {
      addDevice(dev);
    }
    createResourceModels();
  }


  //
  // Resources
  //

  private void createResourceModels() {
    Map<DacBoard, FpgaModel> boards = Maps.newHashMap();

    // build models for all required resources
    for (Channel ch : getChannels()) {
      DacBoard board = ch.getDacBoard();
      FpgaModel fpga = boards.get(board);
      if (fpga == null) {
        if (board instanceof AnalogBoard) {
          fpga = new FpgaModelAnalog((AnalogBoard)board, this);
        } else if (board instanceof MicrowaveBoard) {
          fpga = new FpgaModelMicrowave((MicrowaveBoard)board, this);
        } else if (board instanceof AdcBoard) {
          fpga = new FpgaModelAdc((AdcBoard)board, this);
        } else {
          throw new RuntimeException("Unknown DAC board type for board " + board.getName());
        }
        boards.put(board, fpga);
        addFpga(fpga);
      }
      // connect this channel to the experiment and fpga model
      ch.setExperiment(this);
      ch.setFpgaModel(fpga);
    }

    // build lists of FPGA boards that have or don't have a timing channel
    nonTimerFpgas.addAll(getDacFpgas());
    for (PreampChannel ch : getChannels(PreampChannel.class)) {
      FpgaModelDac fpga = ch.getFpgaModel();
      timerFpgas.add(fpga);
      nonTimerFpgas.remove(fpga);
    }
  }


  //
  // Devices
  //

  private final List<Device> devices = Lists.newArrayList();
  private final Map<String, Device> devicesByName = Maps.newHashMap();

  private void addDevice(Device dev) {
    devices.add(dev);
    devicesByName.put(dev.getName(), dev);
  }

  public Device getDevice(String name) {
    Preconditions.checkArgument(devicesByName.containsKey(name),
        "Device '%s' not found.", name);
    return devicesByName.get(name);
  }

  private List<Device> getDevices() {
    return devices;
  }

  public List<Channel> getChannels() {
    return getChannels(Channel.class);
  }

  public <T extends Channel> List<T> getChannels(Class<T> cls) {
    List<T> channels = Lists.newArrayList();
    for (Device dev : devices) {
      channels.addAll(dev.getChannels(cls));
    }
    return channels;
  }


  //
  // FPGAs
  //

  private final Set<FpgaModel> fpgas = Sets.newHashSet();
  private final Set<FpgaModelDac> timerFpgas = Sets.newHashSet();
  private final Set<FpgaModelDac> nonTimerFpgas = Sets.newHashSet();

  private void addFpga(FpgaModel fpga) {
    fpgas.add(fpga);
  }

  /**
   * Get a list of FPGAs involved in this experiment
   */
  public Set<FpgaModel> getFpgas() {
    return Sets.newHashSet(fpgas);
  }

  public Set<FpgaModelDac> getTimerFpgas() {
    return Sets.newHashSet(timerFpgas);
  }

  public Set<FpgaModelDac> getNonTimerFpgas() {
    return Sets.newHashSet(nonTimerFpgas);
  }

  public Set<FpgaModelMicrowave> getMicrowaveFpgas() {
    Set<FpgaModelMicrowave> fpgas = Sets.newHashSet();
    for (FpgaModel fpga : this.fpgas) {
      if (fpga instanceof FpgaModelMicrowave) {
        fpgas.add((FpgaModelMicrowave)fpga);
      }
    }
    return fpgas;
  }
  
  /**
   * Many operations are only performed on DAC fpgas.
   * @return A set of all FpgaModelDac's in this experiment.
   * @author pomalley
   */
  
  public Set<FpgaModelDac> getDacFpgas() {
	  Set<FpgaModelDac> fpgas = Sets.newHashSet();
	  for (FpgaModel fpga : this.fpgas) {
		  if (fpga instanceof FpgaModelDac) {
			  fpgas.add((FpgaModelDac)fpga);
		  }
	  }
	  return fpgas;
  }
  
  /**
   * Conversely, sometimes we need the ADC fpgas. 
   * @return A set of all FpgaModelAdc's in this experiment.
   * @author pomalley
   */
  public Set<FpgaModelAdc> getAdcFpgas() {
	  Set<FpgaModelAdc> fpgas = Sets.newHashSet();
	  for (FpgaModel fpga : this.fpgas) {
		  if (fpga instanceof FpgaModelAdc) {
			  fpgas.add((FpgaModelAdc)fpga);
		  }
	  }
	  return fpgas;
  }

  public List<String> getFpgaNames() {
    List<String> boardsToRun = Lists.newArrayList();
    for (FpgaModel fpga : fpgas) {
      boardsToRun.add(fpga.getName());
    }
    return boardsToRun;
  }

  private final List<Data> setupPackets = Lists.newArrayList();
  private final List<String> setupState = Lists.newArrayList();
  private List<TimingChannel> timingOrder = null;
  private DacTriggerId autoTriggerId = null;
  private int autoTriggerLen = 0;

  /**
   * Clear all configuration that has been set for this experiment
   */
  public void clearConfig() {
    // reset setup packets
    clearSetupState();

    // clear timing order
    timingOrder = null;

    // clear autotrigger
    autoTriggerId = null;

    // clear configuration on all channels
    for (Device dev : getDevices()) {
      for (Channel ch : dev.getChannels()) {
        ch.clearConfig();
      }
    }
  }


  private void clearSetupState() {
    setupState.clear();
    setupPackets.clear();
  }

  public void setSetupState(List<String> state, List<Data> packets) {
    clearSetupState();
    setupState.addAll(state);
    setupPackets.addAll(packets);
  }

  public List<String> getSetupState() {
    return Lists.newArrayList(setupState);
  }

  public List<Data> getSetupPackets() {
    return Lists.newArrayList(setupPackets);
  }

  public void setAutoTrigger(DacTriggerId id, int length) {
    autoTriggerId = id;
    autoTriggerLen = length;
  }

  public DacTriggerId getAutoTriggerId() {
    return autoTriggerId;
  }

  public int getAutoTriggerLen() {
    return autoTriggerLen;
  }

  public void setTimingOrder(List<TimingChannel> channels) {
    timingOrder = Lists.newArrayList(channels);
  }

  /**
   * Get the order of boards from which to return timing data
   * @return
   */
  public List<String> getTimingOrder() {
    List<String> order = Lists.newArrayList();
    for (TimingChannel ch : getTimingChannels()) {
      order.add(ch.getDacBoard().getName());
    }
    return order;
  }

  public List<TimingChannel> getTimingChannels() {
    return timingOrder != null ? timingOrder : getChannels(TimingChannel.class);
  }

  //
  // Memory
  //

  /**
   * Clear the memory content for this experiment
   * 
   * This only applies to DAC fpgas.
   */
  public void clearMemory() {
    // all memory state is kept in the fpga models, so we clear them out
    for (FpgaModelDac fpga : getDacFpgas()) {
      fpga.clearMemory();
    }
  }

  /**
   * Add bias commands to a set of FPGA boards. Only applies to DACs.
   * @param allCmds
   */
  public void addBiasCommands(ListMultimap<FpgaModelDac, MemoryCommand> allCmds, double delay) {
    // find the maximum number of commands on any single fpga board
    int maxCmds = 0;
    for (FpgaModelDac fpga : allCmds.keySet()) {
      maxCmds = Math.max(maxCmds, allCmds.get(fpga).size());
    }

    // add commands for each board, including noop padding and final delay
    for (FpgaModelDac fpga : getDacFpgas()) {
      List<MemoryCommand> cmds = allCmds.get(fpga); 
      if (cmds != null) {
        fpga.addMemoryCommands(cmds);
        fpga.addMemoryNoops(maxCmds - cmds.size());
      } else {
        fpga.addMemoryNoops(maxCmds);
      }
      if (delay > 0) {
        fpga.addMemoryDelay(delay);
      }
    }
  }

  /**
   * Add a delay in the memory sequence.
   * Only applies to DACs.
   */
  public void addMemoryDelay(double microseconds) {
    for (FpgaModelDac fpga : getDacFpgas()) {
      fpga.addMemoryDelay(microseconds);
    }
  }

  /**
   * Call SRAM. Only applies to DACs.
   */
  public void callSramBlock(String block) {
    for (FpgaModelDac fpga : getDacFpgas()) {
      fpga.callSramBlock(block);
    }
  }

  public void callSramDualBlock(String block1, String block2) {
    for (FpgaModelDac fpga : getDacFpgas()) {
      fpga.callSramDualBlock(block1, block2);
    }
  }

  public void setSramDualBlockDelay(double delay) {
    for (FpgaModelDac fpga : getDacFpgas()) {
      fpga.setSramDualBlockDelay(delay);
    }
  }

  /**
   * Start timer on a set of boards.
   * This only applies to DAC fpgas.
   */
  public void startTimer(List<PreampChannel> channels) {
    Set<FpgaModelDac> starts = Sets.newHashSet();
    Set<FpgaModelDac> noops = getTimerFpgas();
    for (PreampChannel ch : channels) {
      FpgaModelDac fpga = ch.getFpgaModel();
      starts.add(fpga);
      noops.remove(fpga);
    }
    // non-timer boards get started if they have never been started before
    for (FpgaModelDac fpga : getNonTimerFpgas()) {
      if (!fpga.isTimerStarted()) {
        starts.add(fpga);
      } else {
        noops.add(fpga);
      }
    }
    // start the timer on requested boards
    for (FpgaModelDac fpga : starts) {
      fpga.startTimer();
    }
    // insert a no-op on all other boards
    for (FpgaModelDac fpga : noops) {
      fpga.addMemoryNoop();
    }
  }

  /**
   * Stop timer on a set of boards.
   */
  public void stopTimer(List<PreampChannel> channels) {
    Set<FpgaModelDac> stops = Sets.newHashSet();
    Set<FpgaModelDac> noops = getTimerFpgas();
    for (PreampChannel ch : channels) {
      FpgaModelDac fpga = ch.getFpgaModel();
      stops.add(fpga);
      noops.remove(fpga);
    }
    // stop non-timer boards if they are currently running
    for (FpgaModelDac fpga : getNonTimerFpgas()) {
      if (fpga.isTimerRunning()) {
        stops.add(fpga);
      } else {
        noops.add(fpga);
      }
    }
    // stop the timer on requested boards and non-timer boards
    for (FpgaModelDac fpga : stops) {
      fpga.stopTimer();
    }
    // insert a no-op on all other boards
    for (FpgaModelDac fpga : noops) {
      fpga.addMemoryNoop();
    }
  }


  //
  // SRAM
  //


  private List<String> blocks = Lists.newArrayList();
  private Map<String, Integer> blockLengths = Maps.newHashMap();

  public void startSramBlock(String name, long length) {
    blocks.add(name);
    blockLengths.put(name, (int)length);
  }

  public List<String> getBlockNames() {
    return Lists.newArrayList(blocks);
  }

  public int getBlockLength(String name) {
    Preconditions.checkArgument(blockLengths.containsKey(name), "SRAM block '%s' is undefined", name);
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
        return end - 1;
      }
    }
    throw new RuntimeException(String.format("Block '%s' not found", name));
  }
}
