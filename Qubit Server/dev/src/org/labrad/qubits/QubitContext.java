package org.labrad.qubits;

import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;

import org.labrad.AbstractServerContext;
import org.labrad.annotations.Accepts;
import org.labrad.annotations.Returns;
import org.labrad.annotations.Setting;
import org.labrad.annotations.SettingOverload;
import org.labrad.data.Context;
import org.labrad.data.Data;
import org.labrad.data.Record;
import org.labrad.data.Request;
import org.labrad.data.Setters;
import org.labrad.qubits.Experiment.TimingOrderItem;
import org.labrad.qubits.channeldata.AnalogDataFourier;
import org.labrad.qubits.channeldata.AnalogDataTime;
import org.labrad.qubits.channeldata.IqDataFourier;
import org.labrad.qubits.channeldata.IqDataTime;
import org.labrad.qubits.channeldata.TriggerDataTime;
import org.labrad.qubits.channels.*;
import org.labrad.qubits.config.MicrowaveSourceConfig;
import org.labrad.qubits.config.MicrowaveSourceOffConfig;
import org.labrad.qubits.config.SetupPacket;
import org.labrad.qubits.enums.BiasCommandType;
import org.labrad.qubits.enums.DacTriggerId;
import org.labrad.qubits.mem.FastBiasCommands;
import org.labrad.qubits.mem.MemoryCommand;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.resources.MicrowaveSource;
import org.labrad.qubits.resources.Resources;
import org.labrad.qubits.templates.ExperimentBuilder;
import org.labrad.qubits.util.ComplexArray;
import org.labrad.qubits.util.Failure;
import org.labrad.qubits.util.Futures;

import com.google.common.base.Preconditions;
import com.google.common.collect.ArrayListMultimap;
import com.google.common.collect.ListMultimap;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;


public class QubitContext extends AbstractServerContext {

  private Experiment expt = null;
  private Context setupContext = null;

  private Request nextRequest = null;
  private int runIndex;
  private Data lastData = null;

  private boolean configDirty = true;
  private boolean memDirty = true;
  private boolean sramDirty = true;

  /**
   * Initialize this context when it is first created.
   */
  @Override
  public void init() {
    // this is the context in which we will create setup packets
    // we make it different from our own context to avoid potential
    // lockups due to making recursive calls in a context.
    setupContext = new Context(getConnection().getId(), 1);
  }

  @Override
  public void expire() {}


  /**
   * Get the currently-defined experiment in this context.
   */
  private Experiment getExperiment() {
    Preconditions.checkNotNull(expt, "No sequence initialized in this context.");
    return expt;
  }

  /**
   * Set the current experiment in this context
   * @param expt
   */
  private void setExperiment(Experiment expt) {
    this.expt = expt;
  }


  /**
   * Get a channel from the experiment that is of a particular Channel class
   * this unpacks the channel descriptor directly from the incoming LabRAD data
   */
  private <T extends Channel> T getChannel(Data data, Class<T> cls) {
    if (data.matchesType("s")) {
      String device = data.getString();
      return getChannel(device, cls);
    } else if (data.matchesType("ss")) {
      String device = data.get(0).getString();
      String channel = data.get(1).getString();
      return getChannel(device, channel, cls);
    } else {
      throw new RuntimeException("Unknown channel identifier: " + data.pretty());
    }
  }

  /**
   * Get a channel from the experiment that is of a particular class
   */
  private <T extends Channel> T getChannel(String device, String channel, Class<T> cls) {
    return getExperiment().getDevice(device).getChannel(channel, cls);
  }

  /**
   * Get a channel from the experiment that is of a particular class.
   * In this case, no channel name is specified, so this will succeed
   * only if there is a unique channel of the appropriate type.
   */
  private <T extends Channel> T getChannel(String device, Class<T> cls) {
    return getExperiment().getDevice(device).getChannel(cls);
  }

  /**
   * Build a setup packet from a given set of records, using the predefined setup context
   * @param data
   */
  private Data buildSetupPacket(String server, Data records) {
    return Data.clusterOf(
        Data.clusterOf(Data.valueOf(setupContext.getHigh()),
            Data.valueOf(setupContext.getLow())),
            Data.valueOf(server),
            records);
  }

  /**
   * Check the structure of a data object passed in as a setup packet
   */
  private void checkSetupPacket(Data packet) {
    if (!packet.matchesType("(ww)s?")) {
      Failure.fail("Setup packet has invalid format: "
          + "Expected ((ww) s ?{records}) but got %s.", packet.getTag());
    }
    Data records = packet.get(2);
    if (!records.isCluster()) {
      Failure.fail("Setup packet has invalid format: "
          + "Expected a cluster of records but got %s.", records.getTag());
    }
    for (int i = 0; i < records.getClusterSize(); i++) {
      Data record = records.get(i);
      if (!record.matchesType("s?")) {
        Failure.fail("Setup packet has invalid format: "
            + "Expected a cluster of (s{setting} ?{data}) for record %d but got %s",
            i, record.getTag());
      }
    }
  }

  //
  // Echo
  //
  @Setting(id = 99,
      name = "Echo",
      doc = "Echo back.")
      @Returns("?")
      public Data echo(@Accepts("?") Data packet) {
    return packet;
  }


  //
  // Experiment
  //

  @Setting(id = 100,
      name = "Initialize",
      doc = "Initialize a new sequence with the given device and channel setup."
        + "\n\n"
        + "Setup is given by a list of devices, where each device is a cluster "
        + "of name and channel list, and where each channel is a cluster of name "
        + "and cluster of type and parameter list.")
        public void initialize(@Accepts("*(s{dev} *(s{chan} (s{type} *s{params})))") Data template) {
    // build experiment directly from a template
    Resources rsrc = Resources.getCurrent();
    Experiment expt = ExperimentBuilder.fromData(template, rsrc).build();
    setExperiment(expt);
  }


  //
  // Configuration
  //

  @Setting(id = 200,
      name = "New Config",
      doc = "Clear all config calls in this context."
        + "\n\n"
        + "This clears all configuration from the config calls, "
        + "but leaves the device and channel setup unchanged.")
        public void new_config() {
    getExperiment().clearConfig();
    configDirty = true;
  }

  @Setting(id = 210,
      name = "Config Microwaves",
      doc = "Configure the Anritsu settings for the given channel."
        + "\n\n"
        + "Note that if two microwave channels share the same source, "
        + "they must both use the same settings here.  If they do not, "
        + "an error will be thrown when you try to run the sequence.")
        public void config_microwaves(@Accepts({"s", "ss"}) Data id,
            @Accepts("v[GHz]") double freq,
            @Accepts("v[dBm]") double power) {
    // turn the microwave source on, set the power level and frequency
    IqChannel ch = getChannel(id, IqChannel.class);
    ch.configMicrowavesOn(freq, power);
    configDirty = true;
  }
  @SettingOverload
  public void config_microwaves(@Accepts({"s", "ss"}) Data id) {
    // turn the microwave source off
    IqChannel ch = getChannel(id, IqChannel.class);
    ch.configMicrowavesOff();
    configDirty = true;
  }

  @Setting(id = 220,
      name = "Config Preamp",
      doc = "Configure the preamp settings for the given channel."
        + "\n\n"
        + "This includes the DAC offset and polarity, as well as high- "
        + "and low-pass filtering.")
        public void config_preamp(@Accepts({"s", "ss"}) Data id,
            long offset, boolean polarity, String highPass, String lowPass) {
    // set the preamp offset, polarity and filtering options
    PreampChannel ch = getChannel(id, PreampChannel.class);
    ch.setPreampConfig(offset, polarity, highPass, lowPass);
    configDirty = true;
  }

  @Setting(id = 230,
      name = "Config Settling",
      doc = "Configure the deconvolution settling rates for the given channel.")
      public void config_settling(@Accepts({"s", "ss"}) Data id,
          @Accepts("*v[GHz]") double[] rates,
          @Accepts("*v[]") double[] amplitudes) {
    AnalogChannel ch = getChannel(id, AnalogChannel.class);
    ch.setSettling(rates, amplitudes);
    configDirty = true;
  }

  @Setting(id = 240,
      name = "Config Timing Order",
      doc = "Configure the order in which timing results should be returned."
        + "\n\n"
        + "If this option is not specified, timing results will be returned "
        + "for all timing channels in the order they were defined when this "
        + "sequence was initialized.")
        public void config_timing_order(@Accepts({"*s", "*(ss)"}) List<Data> ids) {
    List<TimingOrderItem> channels = Lists.newArrayList();
    for (Data id : ids) {
      int i = -1;
      if (id.isCluster()) {
        if (id.get(1).getString().contains("::")) {
          i = new Integer(id.get(1).getString().substring(id.get(1).getString().lastIndexOf(':') + 1));
          id.get(1).setString(id.get(1).getString().substring(0, id.get(1).getString().lastIndexOf(':') - 1));
        }
      } else {
        if (id.getString().contains("::")) {
          i = new Integer(id.getString().substring(id.getString().lastIndexOf(':') + 1));
          id.setString(id.getString().substring(0, id.getString().lastIndexOf(':') - 1));
        }
      }
      channels.add(new TimingOrderItem(getChannel(id, TimingChannel.class), i));
    }
    getExperiment().setTimingOrder(channels);
    configDirty = true;
  }

  @Setting(id = 250,
      name = "Config Setup Packets",
      doc = "Configure other setup state and packets for this experiment."
        + "\n\n"
        + "Setup information should be specified as a list of token strings "
        + "describing the state that should be setup before this sequence runs, "
        + "and a cluster of packets to be sent to initialize the other "
        + "servers into that state.  Each packet is a cluster of context (ww), "
        + "server name, and cluster of records, where each record is a cluster of "
        + "setting name and data.  These setup packets will get sent before "
        + "this sequence is run, allowing various sequences to be interleaved.")
        public void config_setup_packets(List<String> states, Data packets) {
    List<Data> packetList = Lists.newArrayList();
    for (int i = 0; i < packets.getClusterSize(); i++) {
      Data packet = packets.get(i);
      checkSetupPacket(packet);
      packetList.add(packet);
    }
    getExperiment().setSetupState(states, packetList);
    configDirty = true;
  }

  @Setting(id = 260,
      name = "Config Autotrigger",
      doc = "Configure automatic inclusion of a trigger pulse on every SRAM sequence."
        + "\n\n"
        + "Specifying a trigger channel name (e.g. 'S3') will cause a trigger pulse "
        + "to be automatically added to that channel on every board at the beginning of "
        + "every SRAM sequence.  This can be very helpful when viewing and debugging "
        + "SRAM output on the sampling scope, for example."
        + "\n\n"
        + "You can also specify an optional length for the trigger pulse, which will "
        + "be rounded to the nearest ns.  If no length is specified, the default (16 ns) "
        + "will be used.")
        public void config_autotrigger(String channel) {
    config_autotrigger(channel, Constants.AUTOTRIGGER_PULSE_LENGTH);
    configDirty = true;
  }
  @SettingOverload
  public void config_autotrigger(String channel, @Accepts("v[ns]") double length) {
    getExperiment().setAutoTrigger(DacTriggerId.fromString(channel), (int)length);
    configDirty = true;
  }

  @Setting(id = 280,
      name = "Config Switch Intervals",
      doc = "Configure switching intervals for processing timing data from a particular timing channel.")
      public void config_switch_intervals(@Accepts({"s", "ss"}) Data id,
          @Accepts({"*(v[us], v[us])"}) Data intervals) {
    PreampChannel channel = getChannel(id, PreampChannel.class);
    double[][] ints = new double[intervals.getArraySize()][];
    for (int i = 0; i < ints.length; i++) {
      Data interval = intervals.get(i);
      double a = interval.get(0).getValue();
      double b = interval.get(1).getValue();
      ints[i] = new double[] {a, b};
    }
    channel.setSwitchIntervals(ints);
  }

  @Setting(id = 290,
      name = "Config Critical Phase",
      doc = "Configure the critical phases for processing ADC readout.")
  public void config_critical_phases(@Accepts({"s","ss"}) Data id,
      @Accepts("v{phase}") Data phase) {
    AdcChannel channel = getChannel(id, AdcChannel.class);
    channel.setCriticalPhase(phase.getValue());
  }

  @Setting(id = 291,
      name = "Reverse Critical Phase Comparison",
      doc = "By default we do atan2(Q, I) > criticalPhase. Give this function" +
          "True and we do < instead (for this ADC channel).")
  public void reverse_critical_phase_comparison(@Accepts({"s", "ss"}) Data id,
      @Accepts("b{reverse}") Data reverse) {
    AdcChannel channel = getChannel(id, AdcChannel.class);
    channel.reverseCriticalPhase(reverse.getBool());
  }

  @Setting(id = 292,
      name = "Set IQ Offsets",
      doc = "Bother Dan")
  public void set_iq_offset(@Accepts({"s", "ss"}) Data id, @Accepts("ii") Data offsets) {
    AdcChannel channel = getChannel(id, AdcChannel.class);
    channel.setIqOffset(offsets.get(0).getInt(),offsets.get(1).getInt());
  }

  //
  // Memory
  //
  // these commands allow one to build up memory sequences for FPGA execution.
  // sequences are built up in parallel across all devices involved in
  // the experiment to ensure that all FPGAs remain synchronized when the
  // sequence is executed
  //

  @Setting(id = 300,
      name = "New Mem",
      doc = "Clear memory content in this context.")
      public void new_mem() {
    getExperiment().clearMemory();
    memDirty = true;
  }

  /**
   * Add bias commands in parallel to the specified channels
   * @param commands
   * @param microseconds
   */
  @Setting(id = 310,
      name = "Mem Bias",
      doc = "Adds Bias box commands to the specified channels."
        + "\n\n"
        + "Each bias command is specified as a cluster of channel, command "
        + "name, and voltage level.  As for other settings, the channel can "
        + "be specified as either a device name, or a (device, channel) cluster, "
        + "where the first option is allowed only when there is no ambiguity, "
        + "that is, when there is only one bias channel for the device."
        + "\n\n"
        + "The command name specifies which DAC and mode are to be used for this "
        + "bias command.  Allowed values are 'dac0', 'dac0noselect', 'dac1', and 'dac1slow'.  "
        + "See the FastBias documentation for information about these options."
        + "\n\n"
        + "A final delay can be specified to have a delay command added after the bias "
        + "commands on all memory sequences.  If no final delay is specified, a default "
        + "delay will be added (currently 4.3 microseconds).")
        public void mem_bias(@Accepts({"*(s s v[mV])", "*((ss) s v[mV])"}) List<Data> commands) {
    mem_bias(commands, Constants.DEFAULT_BIAS_DELAY);
    memDirty = true;
  }
  @SettingOverload
  public void mem_bias(@Accepts({"*(s s v[mV])", "*((ss) s v[mV])"}) List<Data> commands,
      @Accepts("v[us]") double microseconds) {
    // create a map with a list of commands for each board
    ListMultimap<FpgaModelDac, MemoryCommand> fpgas = ArrayListMultimap.create();

    // parse the commands and group them for each fpga
    for (Data cmd : commands) {
      FastBiasChannel ch = getChannel(cmd.get(0), FastBiasChannel.class);
      BiasCommandType type = BiasCommandType.fromString(cmd.get(1).getString());
      double voltage = cmd.get(2).getValue();
      fpgas.put(ch.getFpgaModel(), FastBiasCommands.get(type, ch, voltage));
    }

    getExperiment().addBiasCommands(fpgas, microseconds);
    memDirty = true;
  }

  @Setting(id = 320,
      name = "Mem Delay",
      doc = "Add a delay to all channels.")
      public void mem_delay(@Accepts("v[us]") double delay) {
    getExperiment().addMemoryDelay(delay);
    memDirty = true;
  }

  @Setting(id = 321,
    name = "Mem Delay Single",
    doc = "Add a delay to a single channel.")
    public void mem_delay_single(@Accepts({"(s v[us])", "((ss) v[us])"}) Data command) {
      FastBiasChannel ch = getChannel(command.get(0), FastBiasChannel.class);
      double delay_us = command.get(1).getValue();
      getExperiment().addSingleMemoryDelay(ch.getFpgaModel(), delay_us);
      memDirty = true;
  }

  @Setting(id = 330,
      name = "Mem Call SRAM",
      doc = "Call the SRAM block specified by name."
        + "\n\n"
        + "The actual call will not be resolved until the sequence is run, "
        + "so the SRAM blocks do not have to be defined when this call is made."
        + "\n\n"
        + "If running a dual-block SRAM sequence, you must provide the names "
        + "of the first and second blocks (the delay between the END of the first block "
        + "and the START of the second block must be specified separately).")
        public void mem_call_sram(String block) {
    getExperiment().callSramBlock(block);
    memDirty = true;
  }
  @SettingOverload
  public void mem_call_sram(String block1, String block2) {
    getExperiment().callSramDualBlock(block1, block2);
    memDirty = true;
  }

  @Setting(id = 340,
      name = "Mem Start Timer",
      doc = "Start the timer for the specified timing channels.")
      public void mem_start_timer(@Accepts({"*s", "*(ss)"}) List<Data> ids) {
    List<PreampChannel> channels = Lists.newArrayList();
    for (Data ch : ids) {
      channels.add(getChannel(ch, PreampChannel.class));
    }
    getExperiment().startTimer(channels);
    memDirty = true;
  }

  @Setting(id = 350,
      name = "Mem Stop Timer",
      doc = "Stop the timer for the specified timing channels.")
      public void mem_stop_timer(@Accepts({"*s", "*(ss)"}) List<Data> ids) {
    List<PreampChannel> channels = Lists.newArrayList();
    for (Data ch : ids) {
      channels.add(getChannel(ch, PreampChannel.class));
    }
    getExperiment().stopTimer(channels);
    memDirty = true;
  }

  @Setting(id = 360,
      name = "Mem Sync Delay",
      doc = "Adds a memory delay to synchronize all channels.  Call last in the memory sequence.")
    public void mem_sync_delay() {

      getExperiment().addMemSyncDelay();
      memDirty = true;
  }
  //
  // Jump Table
  //

  @Setting(id = 370,
           name = "Clear Jump Table",
           doc = "Clear the jump table commands in this context.")
  public void clear_jump_table() {
    getExperiment().clearJumpTable();
  }

  @Setting(id = 371,
           name = "Add Jump Table Entry",
           doc = "Add a jump table entry to a single board.")
  public void add_jump_table_entry(@Accepts({"s", "(ss)"}) Data channel,
                                   String command_name,
                                   @Accepts({"w{NOP,END}", "ww{IDLE}", "www{JUMP}", "wwww{CYCLE}"}) Data command_data) {
    SramChannelBase ch = getChannel(channel, SramChannelBase.class);
    ch.addJumpTableEntry(command_name, command_data);
  }

  @Setting(id = 372,
           name = "Set Jump Table Counters",
           doc = "Set the counter values for this board")
  public void set_jump_table_counters(@Accepts({"s", "(ss)"}) Data channel,
                                      @Accepts("*w") Data counters) {
    SramChannelBase ch = getChannel(channel, SramChannelBase.class);
    ch.setCounters(counters.getWordArray());
  }



  //
  // SRAM
  //

  /**
   * Start a new named SRAM block.
   */
  @Setting(id = 400,
      name = "New SRAM Block",
      doc = "Create a new SRAM block with the specified name and length, for this channel."
        + "\n\n"
        + "All subsequent SRAM calls will affect this block, until a new block "
        + "is created.  If you do not provide SRAM data for a particular channel, "
        + "it will be filled with zeros (and deconvolved).  If the length is not "
        + "a multiple of 4, the data will be padded at the beginning after "
        + "deconvolution.")
        public void new_sram_block(String name, long length, @Accepts({"ss"}) Data id) {

    @SuppressWarnings("rawtypes")
    SramChannelBase ch = getChannel(id, SramChannelBase.class);
    ch.getFpgaModel().startSramBlock(name, length);
    ch.setCurrentBlock(name);
    sramDirty = true;
  }

  @Setting(id = 401,
      name = "SRAM Dual Block Delay",
      doc = "Set the delay between the first and second blocks of a dual-block SRAM command."
        + "\n\n"
        + "Note that if dual-block SRAM is used in a given sequence, there can only be one "
        + "such call, so that this command sets the delay regardless of the block names.  "
        + "Also note that this delay will be rounded to the nearest integral number of "
        + "nanoseconds which may give unexpected results if the delay is converted from "
        + "another unit of time.")
        public void sram_dual_block_delay(@Accepts("v[ns]") double delay) {
    getExperiment().setSramDualBlockDelay(delay);
    sramDirty = true;
  }


  /**
   * Add SRAM data for a microwave IQ channel.
   */
  @Setting(id = 410,
      name = "SRAM IQ Data",
      doc = "Set IQ data for the specified channel."
        + "\n\n"
        + "The data is specified as a list of complex numbers, "
        + "with the real and imaginary parts giving the I and Q "
        + "microwave quadratures.  The length of the data should "
        + "match the length of the current SRAM block.  "
        + "An optional boolean specifies whether the data "
        + "should be deconvolved (default: true)."
        + "If deconvolve=false, the data can be specified as DAC-ready"
        + "I and Q integers.")
        public void sram_iq_data(@Accepts({"s", "ss"}) Data id,
            @Accepts("*c") Data vals) {
    sram_iq_data(id, vals, true);
    sramDirty = true;
  }
  @SettingOverload
  public void sram_iq_data(@Accepts({"s", "ss"}) Data id,
      @Accepts({"*c", "(*i{I}, *i{Q})"}) Data vals,
      boolean deconvolve) {
    IqChannel ch = getChannel(id, IqChannel.class);
    if (vals.isCluster()) {
      Preconditions.checkArgument(!deconvolve, "Must not deconvolve if providing DAC'ified IQ data.");
      ch.addData(new IqDataTime(vals.get(0).getIntArray(), vals.get(1).getIntArray()));
    } else {
      ComplexArray c = ComplexArray.fromData(vals);
      ch.addData(new IqDataTime(c, !deconvolve));
    }
    sramDirty = true;
  }


  /**
   * Add SRAM data for a microwave IQ channel in Fourier representation.
   */
  @Setting(id = 411,
      name = "SRAM IQ Data Fourier",
      doc = "Set IQ data in Fourier representation for the specified channel."
        + "\n\n"
        + "The data is specified as a list of complex numbers, "
        + "with the real and imaginary parts giving the I and Q "
        + "microwave quadratures.  The length of the data should "
        + "match the length of the current SRAM block.")
        public void sram_iq_data_fourier(@Accepts({"s", "ss"}) Data id,
            @Accepts("*c") Data vals,
            @Accepts("v[ns]") double t0) {
    IqChannel ch = getChannel(id, IqChannel.class);
    ComplexArray c = ComplexArray.fromData(vals);
    ch.addData(new IqDataFourier(c, t0));
    sramDirty = true;
  }


  /**
   * Add SRAM data for an analog channel
   */
  @Setting(id = 420,
      name = "SRAM Analog Data",
      doc = "Set analog data for the specified channel."
        + "\n\n"
        + "The length of the data should match the length of the "
        + "current SRAM block.  An optional boolean specifies "
        + "whether the data should be deconvolved (default: true)."
        + "If deconvolve=false, the data can be supplied as DAC-ready"
        + "integers")
        public void sram_analog_data(@Accepts({"s", "ss"}) Data id,
            @Accepts("*v") Data vals) {
    sram_analog_data(id, vals, true);
    sramDirty = true;
  }
  @SettingOverload
  public void sram_analog_data(@Accepts({"s", "ss"}) Data id,
      @Accepts({"*v", "*i"}) Data vals,
      boolean deconvolve) {
    AnalogChannel ch = getChannel(id, AnalogChannel.class);
    if (vals.matchesType("*v")) {
      double[] arr = vals.getValueArray();
      ch.addData(new AnalogDataTime(arr, !deconvolve));
    } else {
      Preconditions.checkArgument(!deconvolve, "Must not deconvolve if providing DAC'ified data.");
      int[] arr = vals.getIntArray();
      ch.addData(new AnalogDataTime(arr));
    }
    sramDirty = true;
  }


  /**
   * Add SRAM data for an analog channel in Fourier representation
   */
  @Setting(id = 421,
      name = "SRAM Analog Data Fourier",
      doc = "Set analog data in Fourier representation for the specified channel."
        + "\n\n"
        + "Because this represents real data, we only need half as many samples.  "
        + "In particular, for a sequence of length n, the fourier data given "
        + "here must have length n/2+1 (n even) or (n+1)/2 (n odd).")
        public void sram_analog_fourier_data(@Accepts({"s", "ss"}) Data id,
            @Accepts("*c") Data vals,
            @Accepts("v[ns]") double t0) {
    AnalogChannel ch = getChannel(id, AnalogChannel.class);
    ComplexArray c = ComplexArray.fromData(vals);
    ch.addData(new AnalogDataFourier(c, t0));
    sramDirty = true;
  }


  // triggers

  @Setting(id = 430,
      name = "SRAM Trigger Data",
      doc = "Set trigger data for the specified trigger channel")
      public void sram_trigger_data(@Accepts({"s", "ss"}) Data id,
          @Accepts("*b") Data data) {
    TriggerChannel ch = getChannel(id, TriggerChannel.class);
    ch.addData(new TriggerDataTime(data.getBoolArray()));
    sramDirty = true;
  }

  @Setting(id = 431,
      name = "SRAM Trigger Pulses",
      doc = "Set trigger data as a series of pulses for the specified trigger channel"
        + "\n\n"
        + "Each pulse is given as a cluster of (start, length) values, "
        + "specified in nanoseconds.")
        public void sram_trigger_pulses(@Accepts({"s", "ss"}) Data id,
            @Accepts("*(v[ns] v[ns])") List<Data> pulses) {
    TriggerChannel ch = getChannel(id, TriggerChannel.class);
    for (Data pulse : pulses) {
      int start = (int)pulse.get(0).getValue();
      int length = (int)pulse.get(1).getValue();
      ch.addPulse(start, length);
    }
    sramDirty = true;
  }

  //
  // ADC settings
  //

  @Setting(id = 510,
      name = "Set Start Delay",
      doc = "Sets the SRAM start delay for this channel; valid for ADC, IQ, and analog channels. " +
      "First argument {s or (ss)}: channel (either device name or (device name, channel name) " +
      "Second: delay, in clock cycles (typically 4 ns) (w)")
  public void adc_set_start_delay(@Accepts({"s", "ss"}) Data id,
      @Accepts("i") int delay) {
    StartDelayChannel ch = getChannel(id, StartDelayChannel.class);
    ch.setStartDelay(delay);
  }

  @Setting(id = 520,
      name = "ADC Set Mode",
      doc = "Sets the mode of this channel.\n " +
      "First argument {s or (ss)}: channel (either device name or (device name, channel name)\n " +
  "Second {s or (si)}: either 'demodulate' or ('average', [demod channel number])")
  public void adc_set_mode(@Accepts({"s", "ss"}) Data id,
      @Accepts({"s", "si"}) Data mode) {
    AdcChannel ch = getChannel(id, AdcChannel.class);
    if (mode.isString()) {
      ch.setToAverage();
    } else {
      ch.setToDemodulate(mode.get(1).getInt());
    }
  }

  @Setting(id = 530,
      name = "ADC Set Filter Function",
      doc = "Sets the filter function for this channel; must be an adc channel in demod mode.\n " +
      "First argument {s or (ss)}: channel (either device name or (device name, channel name)\n " +
      "Second {s}: the filter function, represented as a string\n " +
      "Third {w}: the length of the stretch\n " +
  "Fourth {w}: the index at which to stretch")
  public void adc_set_filter_function(@Accepts({"s", "ss"}) Data id,
      @Accepts("s") Data bytes,
      @Accepts("w") Data stretchLen,
      @Accepts("w") Data stretchAt) {
    AdcChannel ch = getChannel(id, AdcChannel.class);
    ch.setFilterFunction(bytes.getString(), (int)stretchLen.getWord(), (int)stretchAt.getWord());
  }

  @Setting(id = 531,
      name = "ADC Set Trig Magnitude",
      doc = "Sets the filter function for this channel. Must be an adc channel in demod mode "
        + "and the sub-channel must be valid (i.e. under 4 for build 1). "
        + "sineAmp and cosineAmp range from 0 to 255.\n" +
        "First argument {s or (ss)}: channel (either device name or (device name, channel name)\n " +
        "Second {w}: sine amplitude\n " +
        "Third {w}: cosine amplitude\n")
  public void adc_set_trig_magnitude(@Accepts({"s", "ss"}) Data id,
      @Accepts("w") Data sineAmp,
      @Accepts("w") Data cosineAmp) {
    AdcChannel ch = getChannel(id, AdcChannel.class);
    ch.setTrigMagnitude((int)sineAmp.getWord(), (int)cosineAmp.getWord());
  }

  @Setting(id = 532,
      name = "ADC Demod Phase",
      doc = "Sets the demodulation phase. Must be an adc channel in demod mode.\n"
        + "See the documentation for this in the GHz FPGA server.\n" +
        "First argument {s or (ss)}: channel (either device name or (device name, channel name)\n " +
        "Second {(i,i) or (v[Hz], v[rad])}: (dPhi, phi0) or (frequency (Hz), offset (radians))")
  public void adc_demod_phase(@Accepts({"s", "ss"}) Data id,
      @Accepts({"ii", "v[Hz]v[rad]"}) Data dat) {
    AdcChannel ch = getChannel(id, AdcChannel.class);
    if (dat.matchesType("(ii)")) {
      ch.setPhase(dat.get(0).getInt(), dat.get(1).getInt());
    } else {
      ch.setPhase(dat.get(0).getValue(), dat.get(1).getValue());
    }
  }

  @Setting(id = 533, name = "ADC Trigger Table",
      doc = "Pass through to GHz FPGA server's ADC Trigger Table.\n" +
          "data: List of (count,delay,length,rchan) tuples.")
  public void adc_trigger_table(@Accepts({"s", "ss"}) Data id,
      @Accepts("*(i,i,i,i)") Data data) {
    AdcChannel ch = getChannel(id, AdcChannel.class);
    ch.setTriggerTable(data);
  }

  @Setting(id = 534, name = "ADC Mixer Table",
      doc = "Pass through to GHz FPGA server's ADC Mixer Table.\n" +
          "data: List of (count,delay,length,rchan) tuples.")
  public void adc_mixer_table(@Accepts({"s", "ss"}) Data id,
      @Accepts("*2i {Nx2 array of IQ values}") Data data) {
    AdcChannel ch = getChannel(id, AdcChannel.class);
    ch.setMixerTable(data);
  }

  //
  // put the sequence together
  //

  @Setting(id = 900,
      name = "Build Sequence",
      doc = "Compiles SRAM and memory sequences into runnable form."
        + "\n\n"
        + "Any problems with the setup (for example, conflicting microwave "
        + "settings for two channels that use the same microwave source) "
        + "will be detected at this point and cause an error to be thrown.")
        public void build_sequence() throws InterruptedException, ExecutionException {

    Experiment expt = getExperiment();

    //
    // sanity checks
    //

    //
    // if we don't have any preamp channels, add a start/stop timer to all boards.
    // pomalley 5/10/11
    //
    /* Disabled because we don't use timing packets any more -- ERJ
    if (expt.getTimerFpgas().size() == 0) {
      expt.startTimer(new ArrayList<PreampChannel>());
      expt.stopTimer(new ArrayList<PreampChannel>());
    }

    // check timer state of each involved fpga
    for (FpgaModelDac fpga : expt.getDacFpgas()) {
      fpga.checkTimerStatus();
    }*/

    // check microwave source configuration
    Map<MicrowaveSource, MicrowaveSourceConfig> uwaveConfigs = Maps.newHashMap();
    for (IqChannel ch : expt.getChannels(IqChannel.class)) {
      MicrowaveSource src = ch.getMicrowaveSource();
      MicrowaveSourceConfig config = ch.getMicrowaveConfig();
      Preconditions.checkNotNull(config, "No microwaves configured for channel '%s'", ch.getName());
      if (!uwaveConfigs.containsKey(src)) {
        // keep track of which microwave sources we have seen
        uwaveConfigs.put(src, config);
      } else {
        // check that microwave configurations are compatible
        Preconditions.checkState(config.equals(uwaveConfigs.get(src)),
            "Conflicting microwave configurations for source '%s'", src.getName());
      }
    }
    // turn off the microwave source for any boards whose source is not configured
    for (FpgaModelMicrowave fpga : getExperiment().getMicrowaveFpgas()) {
      MicrowaveSource src = fpga.getMicrowaveSource();
      if (!uwaveConfigs.containsKey(src)) {
        uwaveConfigs.put(src, new MicrowaveSourceOffConfig());
      }
    }


    //
    // build setup packets
    //

    // start with setup packets that have already been configured
    List<Data> setupPackets = Lists.newArrayList(expt.getSetupPackets());
    List<String> setupState = Lists.newArrayList(expt.getSetupState());

    // build setup packets for microwave sources
    // TODO if a microwave source is used for dummy channels and real channels, resolve here
    Request anristuRequest = Request.to(Constants.ANRITSU_SERVER);
    anristuRequest.add("List Devices");
    List<Data> anritsuList = getConnection().sendAndWait(anristuRequest).get(0).getDataList();
    HashSet<String> anritsuNames = new HashSet<String>();
    for (Data d : anritsuList) {
      anritsuNames.add(d.get(1).getString());
      //System.out.println("Anritsu Device: '" + d.get(1).getString() + "'");
    }
    Request hittiteRequest = Request.to(Constants.HITTITE_SERVER);
    hittiteRequest.add("List Devices");
    List<Data> hittiteList = getConnection().sendAndWait(hittiteRequest).get(0).getDataList();
    HashSet<String> hittiteNames = new HashSet<String>();
    for (Data d : hittiteList) {
      hittiteNames.add(d.get(1).getString());
      //System.out.println("Hittite Device: '" + d.get(1).getString() + "'");
    }
    for (Map.Entry<MicrowaveSource, MicrowaveSourceConfig> entry : uwaveConfigs.entrySet()) {
      SetupPacket p = entry.getValue().getSetupPacket(entry.getKey());
      String devName = entry.getKey().getName();
      if (anritsuNames.contains(devName)) {
        setupPackets.add(buildSetupPacket(Constants.ANRITSU_SERVER, p.getRecords()));
      } else if (hittiteNames.contains(devName)) {
        setupPackets.add(buildSetupPacket(Constants.HITTITE_SERVER, p.getRecords()));
      } else {
        Preconditions.checkState(false, "Microwave device not found: '%s'", devName);
      }

      setupState.add(p.getState());
    }

    // build setup packets for preamp boards
    // TODO improve DC Racks server (e.g. need caching)
    for (PreampChannel ch : expt.getChannels(PreampChannel.class)) {
      if (ch.hasPreampConfig()) {
        SetupPacket p = ch.getPreampConfig().getSetupPacket(ch);
        setupPackets.add(buildSetupPacket(Constants.DC_RACK_SERVER, p.getRecords()));
        setupState.add(p.getState());
      }
    }


    //
    // deconvolve SRAM sequences
    //

    // this is the new-style deconvolution routine which sends all deconvolution requests in separate packets
    DeconvolutionProxy deconvolver = new DeconvolutionProxy(getConnection());
    List<Future<Void>> deconvolutions = Lists.newArrayList();
    for (FpgaModelDac fpga : expt.getDacFpgas()) {
      // pomalley 4/22/14 added this check, as we now handle the case of boards not having defined channels a bit differently
      if (fpga.hasSramChannel()) {
        deconvolutions.add(fpga.deconvolveSram(deconvolver));
      }
    }
    Futures.waitForAll(deconvolutions).get();


    //
    // build run packet
    //

    Request runRequest = Request.to(Constants.GHZ_DAC_SERVER, getContext());

    // NEW 4/22/2011 - pomalley
    // settings for ADCs
    for (FpgaModelAdc fpga : expt.getAdcFpgas()) {
      runRequest.add("Select Device", Data.valueOf(fpga.getName()));
      fpga.addPackets(runRequest);
      //AdcBaseConfig conf = fpga.getChannel().getConfig();
      //Preconditions.checkState(conf != null, "ADC channel '%s' was not configured!", fpga.getChannel().getName());
      //fpga.getChannel().getConfig().addPackets(runRequest);
    }

    // upload all memory and SRAM data
    for (FpgaModelDac fpga : expt.getDacFpgas()) {
      runRequest.add("Select Device", Data.valueOf(fpga.getName()));
      // TODO: how to handle backwards compatibility for non-JT boards?
//      runRequest.add("Start Delay", Data.valueOf((long)fpga.getStartDelay()));  // new 5/4/11 - pomalley
//      runRequest.add("Memory", Data.valueOf(fpga.getMemory()));
      fpga.addJumpTablePackets(runRequest);
      Preconditions.checkState(!fpga.hasDualBlockSram(), "No dual block with the jump table!"); // TODO: blargh
      if (fpga.hasDualBlockSram()) {
        runRequest.add("SRAM dual block",
            Data.valueOf(fpga.getSramDualBlock1()),
            Data.valueOf(fpga.getSramDualBlock2()),
            Data.valueOf(fpga.getSramDualBlockDelay()));
      } else {
        runRequest.add("SRAM", Data.valueOf(fpga.getSram()));
      }
    }

    // set up daisy chain and timing order
    runRequest.add("Daisy Chain", Data.listOf(expt.getFpgaNames(), Setters.stringSetter));
    runRequest.add("Timing Order", Data.listOf(expt.getTimingOrder(), Setters.stringSetter));

    // run the sequence
    runIndex = runRequest.addRecord("Run Sequence",
        Data.valueOf(0L), // put in a dummy value for number of reps
        Data.valueOf(true), // return timing results
        Data.clusterOf(setupPackets),
        Data.listOf(setupState, Setters.stringSetter));
    nextRequest = runRequest;

    // clear the dirty bits
    configDirty = false;
    memDirty = false;
    sramDirty = false;
  }

  @Setting(id = 1009,
      name = "Get SRAM Final",
      doc = "Make sure to run build sequence first.")
      public Data get_sram_final(@Accepts({"s", "ss"}) Data id)
  {
    IqChannel iq = getChannel(id, IqChannel.class);
    return Data.valueOf(iq.getFpgaModel().getSram());
  }

  @Setting(id = 1000,
      name = "Run",
      doc = "Runs the current sequence by sending to the GHz DACs server."
        + "\n\n"
        + "Note that no timing data are returned here.  You must call one or more "
        + "of the 'Get Data *' methods to retrieve the data in the desired format.")
  public void run_experiment(long reps) throws InterruptedException, ExecutionException {
    Preconditions.checkArgument(reps > 0, "Reps must be a positive integer");
    if (configDirty || memDirty || sramDirty) {
      build_sequence();
    }
    nextRequest.getRecord(runIndex).getData().setWord(reps, 0);
    lastData = getConnection().sendAndWait(nextRequest).get(runIndex);
  }

  @Setting(id = 1001,
      name = "Run DAC SRAM",
      doc = "Similar to 'Run', but does dac_run_sram instead of run_sequence. This simply runs the " +
  "DAC SRAM (once or repeatedly) and gives no data back. Used to determine the power output, etc.")
  public void run_dac_sram(@Accepts("*w") Data data,
      @Accepts("b") Data loop) throws InterruptedException, ExecutionException {

    if (configDirty || memDirty || sramDirty) {
      build_sequence();
    }

    // change the run request to dac_run_sram request
    nextRequest.getRecords().remove(runIndex);
    nextRequest.add("DAC Run SRAM", data, loop);

    getConnection().sendAndWait(nextRequest);
  }

  @Setting(id = 1002,
      name = "ADC Run Demod",
      doc = "Builds the sequence and runs ADC Run Demod")
  @Returns("*3i{I,Q}, *i{pktCounters}, *i{readbackCounters}")
  public Data adc_run_demod(@Accepts("s") Data mode) throws InterruptedException, ExecutionException {
    if (configDirty || memDirty || sramDirty) {
      build_sequence();
    }
    nextRequest.getRecords().remove(runIndex);
    nextRequest.add("ADC Run Demod", mode);
    return getConnection().sendAndWait(nextRequest).get(nextRequest.size()-1);
  }
  @SettingOverload
  public Data adc_run_demod() throws InterruptedException, ExecutionException {
    return adc_run_demod(Data.valueOf("iq"));
  }

  @Setting(id = 1100,
      name = "Get Data Raw",
      doc = "Gets the raw timing data from the previous run. Given a deinterlace argument, only DAC data are returned")
      @Returns("*4i")
      public Data get_data_raw() {
    return lastData;
  }

  @Setting(id = 1112,
      name = "Get Data Raw Phases",
      doc = "Gets the raw data from the ADC results, converted to phases.")
      @Returns("*3v[rad]")
  public Data get_data_raw_phases() {
    double[][][] ans = extractDataPhases();
    return Data.valueOf(ans, "rad");
  }
    
  private double[][][] extractDataPhases() {
    int[] shape = lastData.getArrayShape();
    double[][][] ans = new double[shape[0]][shape[1]][];
    List<Integer> adcIndices = this.getExperiment().adcTimingOrderIndices();
    for (int whichAdcChannel = 0; whichAdcChannel < shape[0]; whichAdcChannel++) {

      AdcChannel ch = (AdcChannel)this.getExperiment().getTimingChannels().get(adcIndices.get(whichAdcChannel)).getChannel();
      for (int j=0; j<shape[1]; j++) {
        ans[whichAdcChannel][j] = ch.getPhases(
            lastData.get(whichAdcChannel, j, 0).getIntArray(),
            lastData.get(whichAdcChannel, j, 1).getIntArray()
            );
      }
    }
    return ans;
  }

  //
  // diagnostic information
  //

  @Setting(id = 2001,
      name = "Dump Sequence Packet",
      doc = "Returns a dump of the packet to be sent to the GHz DACs server."
        + "\n\n"
        + "The packet dump is a cluster of records where each record is itself "
        + "a cluster of (name, data).  For a human-readable dump of the packet, "
        + "see the 'Dump Sequence Text' setting.")
        public Data dump_packet() {
    List<Data> records = Lists.newArrayList();
    for (Record r : nextRequest.getRecords()) {
      records.add(Data.clusterOf(Data.valueOf(r.getName()),
          r.getData()));
    }
    return Data.clusterOf(records);
  }

  @Setting(id = 2002,
      name = "Dump Sequence Text",
      doc = "Returns a dump of the current sequence in human-readable form")
      @Returns("s")
      public Data dump_text() {

    List<String> deviceNames = Lists.newArrayList();
    Map<String, long[]> memorySequences = Maps.newHashMap();
    Map<String, long[]> sramSequences = Maps.newHashMap();
    List<Record> commands = Lists.newArrayList();

    // iterate over packet, pulling out commands
    String currentDevice = null;
    for (Record r : nextRequest.getRecords()) {
      String cmd = r.getName();
      if ("Select Device".equals(cmd)) {
        currentDevice = r.getData().getString();
        deviceNames.add(currentDevice);
      } else if ("Memory".equals(cmd)) {
        memorySequences.put(currentDevice, r.getData().getWordArray());
      } else if ("SRAM".equals(cmd)) {
        sramSequences.put(currentDevice, r.getData().getWordArray());
      } else if ("SRAM Address".equals(cmd)) {
        // do nothing
      } else {
        commands.add(r);
      }
    }
    Collections.sort(deviceNames);

    List<String> lines = Lists.newArrayList();

    StringBuilder devLine = new StringBuilder();
    for (String dev : deviceNames) {
      devLine.append(dev);
      devLine.append(", ");
    }
    lines.add(devLine.toString());
    lines.add("");

    lines.add("Memory");
    if (deviceNames.size() > 0) {
      int N = memorySequences.get(deviceNames.get(0)).length;
      for (int i = 0; i < N; i++) {
        StringBuilder row = new StringBuilder();
        for (String name : deviceNames) {
          row.append(String.format("%06X", memorySequences.get(name)[i]));
          row.append("  ");
        }
        lines.add(row.toString());
      }
    }
    lines.add("");

    lines.add("SRAM");
    if (deviceNames.size() > 0) {
      int N = sramSequences.get(deviceNames.get(0)).length;
      for (int i = 0; i < N; i++) {
        StringBuilder row = new StringBuilder();
        for (String name : deviceNames) {
          row.append(String.format("%08X", sramSequences.get(name)[i]));
          row.append("  ");
        }
        lines.add(row.toString());
      }
    }
    lines.add("");

    for (Record r : commands) {
      lines.add(r.getName());
      lines.add(r.getData().toString());
      lines.add("");
    }

    StringBuilder builder = new StringBuilder();
    for (String line : lines) {
      builder.append(line);
      builder.append("\n");
    }
    return Data.valueOf(builder.toString());
  }
}
