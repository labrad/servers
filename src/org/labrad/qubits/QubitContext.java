package org.labrad.qubits;

import java.util.Arrays;
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
import org.labrad.qubits.channeldata.AnalogDataFourier;
import org.labrad.qubits.channeldata.AnalogDataTime;
import org.labrad.qubits.channeldata.IqDataFourier;
import org.labrad.qubits.channeldata.IqDataTime;
import org.labrad.qubits.channeldata.TriggerDataTime;
import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.channels.Channel;
import org.labrad.qubits.channels.FastBiasChannel;
import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.channels.PreampChannel;
import org.labrad.qubits.channels.TriggerChannel;
import org.labrad.qubits.config.MicrowaveSourceConfig;
import org.labrad.qubits.config.MicrowaveSourceOffConfig;
import org.labrad.qubits.config.SetupPacket;
import org.labrad.qubits.enums.BiasCommandType;
import org.labrad.qubits.enums.DacTriggerId;
import org.labrad.qubits.mem.FastBiasCommands;
import org.labrad.qubits.mem.MemoryCommand;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.proxies.RegistryProxy;
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

  @SuppressWarnings("unused")
  private ExperimentBuilder builder = null;
  private final Object builderLock = new Object();
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
   * Get the currently-defined experiment builder.
   */
  /*
  private ExperimentBuilder getExperimentBuilder() {
    synchronized (builderLock) {
      Preconditions.checkNotNull(builder, "No sequence initialized in this context.");
      return builder;
    }
  }
  */
  
  /**
   * Set the current experiment to a new one when one is created.
   * @param expt
   */
  private void setExperimentBuilder(ExperimentBuilder builder) {
    synchronized (builderLock) {
      this.builder = builder;
    }
  }
  
  
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
  // Experiment
  //

  @Setting(id = 100,
           name = "Initialize",
           doc = "Initialize a new sequence with the given device and channel setup."
               + "\n\n"
               + "You can specify a path and a list of string names.  Devices with those names "
               + "will be loaded from the registry at the specified path, relative to "
               + "the current directory in this context.  You can optionally specify "
               + "another list of strings to be used as aliases for those devices "
               + "in this context.  For example, in the registry we might have devices called "
               + "['Fridge qubit A', 'Fridge qubit B',...], but we could alias them for a "
               + "particular experiment to be called ['q0', 'q1',...]."
               + "\n\n"
               //+ "The other possibility is to specify another context from which to copy "
               //+ "the setup.  This will copy only the device and channel definitions, not "
               //+ "any configuration, memory, or SRAM setup."
               //+ "\n\n"
               + "Alternatively, you can provide the device and channel definitions directly.  "
               + "You do this by giving a list of devices, where each device is a cluster "
               + "of name and channel list, and where each channel is a cluster of name "
               + "and cluster of type and parameter list.")
  public void initialize(List<String> path, List<String> names) {
    // load devices from the registry
    initialize(path, names, names);
  }
  @SettingOverload
  public void initialize(List<String> path, List<String> names, List<String> aliases) {
    // load devices from the registry, but call them by different names
    Data template = RegistryProxy.loadDevices(path, names, aliases, getConnection(), getContext());
    initialize(template);
  }
  //@SettingOverload
  //public void initialize(long high, long low) {
  //	// copy the experiment defined in another context
  //	QubitContext ctx = (QubitContext)getServerContext(new Context(low, high));
  //	initialize(ctx.getExperimentBuilder());
  //}
  @SettingOverload
  public void initialize(@Accepts("*(s{dev} *(s{chan} (s{type} *s{params})))") Data template) {
    // build experiment directly from a template
    Resources rsrc = Resources.getCurrent();
    initialize(ExperimentBuilder.fromData(template, rsrc));
  }
  public void initialize(ExperimentBuilder builder) {
    Experiment expt = builder.build();
    setExperimentBuilder(builder);
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
                              @Accepts("*v[GHz]") double[] amplitudes) {
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
    List<PreampChannel> channels = Lists.newArrayList();
    for (Data id : ids) {
      channels.add(getChannel(id, PreampChannel.class));
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
    ListMultimap<FpgaModel, MemoryCommand> fpgas = ArrayListMultimap.create();

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


  //
  // SRAM
  //

  private String currentBlock;

  /**
   * Start a new named SRAM block.
   */
  @Setting(id = 400,
           name = "New SRAM Block",
           doc = "Create a new SRAM block with the specified name and length."
               + "\n\n"
               + "All subsequent SRAM calls will affect this block, until a new block "
               + "is created.  If you do not provide SRAM data for a particular channel, "
               + "it will be filled with zeros (and deconvolved).  If the length is not "
               + "a multiple of 4, the data will be padded at the beginning after "
               + "deconvolution.")
  public void new_sram_block(String name, long length) {
    getExperiment().startSramBlock(name, length);
    currentBlock = name;
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
               + "should be deconvolved (default: true).")
  public void sram_iq_data(@Accepts({"s", "ss"}) Data id,
                           @Accepts("*c") Data vals) {
    sram_iq_data(id, vals, true);
    sramDirty = true;
  }
  @SettingOverload
  public void sram_iq_data(@Accepts({"s", "ss"}) Data id,
                           @Accepts("*c") Data vals,
                           boolean deconvolve) {
    IqChannel ch = getChannel(id, IqChannel.class);
    ComplexArray c = ComplexArray.fromData(vals);
    ch.addData(currentBlock, new IqDataTime(c, !deconvolve));
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
    ch.addData(currentBlock, new IqDataFourier(c, t0));
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
               + "whether the data should be deconvolved (default: true).")
  public void sram_analog_data(@Accepts({"s", "ss"}) Data id,
                               @Accepts("*v") Data vals) {
    sram_analog_data(id, vals, true);
    sramDirty = true;
  }
  @SettingOverload
  public void sram_analog_data(@Accepts({"s", "ss"}) Data id,
      @Accepts("*v") Data vals,
      boolean deconvolve) {
    AnalogChannel ch = getChannel(id, AnalogChannel.class);
    double[] arr = vals.getValueArray();
    ch.addData(currentBlock, new AnalogDataTime(arr, !deconvolve));
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
    ch.addData(currentBlock, new AnalogDataFourier(c, t0));
    sramDirty = true;
  } 


  // triggers

  @Setting(id = 430,
           name = "SRAM Trigger Data",
           doc = "Set trigger data for the specified trigger channel")
  public void sram_trigger_data(@Accepts({"s", "ss"}) Data id,
                                @Accepts("*b") Data data) {
    TriggerChannel ch = getChannel(id, TriggerChannel.class);
    ch.addData(currentBlock, new TriggerDataTime(data.getBoolArray()));
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
      ch.addPulse(currentBlock, start, length);
    }
    sramDirty = true;
  }


  //
  // put the sequence together
  //

  @Setting(id = 900,
           name = "Build Sequence",
           doc = "Compiles SRAM and memory sequences into runnable form")
  public void build_sequence() throws InterruptedException, ExecutionException {

    Experiment expt = getExperiment();

    //
    // sanity checks
    //

    // check timer state of each involved fpga
    for (FpgaModel fpga : expt.getFpgas()) {
      fpga.checkTimerStatus();
    }

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
    // loop over microwave boards, and turn off the microwave source for any boards whose source is not configured
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
    for (MicrowaveSource src : uwaveConfigs.keySet()) {
      SetupPacket p = uwaveConfigs.get(src).getSetupPacket(src);
      setupPackets.add(buildSetupPacket(Constants.ANRITSU_SERVER, p.getRecords()));
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
    for (FpgaModel fpga : expt.getFpgas()) {
      deconvolutions.add(fpga.deconvolveSram(deconvolver));
    }
    Futures.waitForAll(deconvolutions).get();


    //
    // build run packet
    //

    Request runRequest = Request.to(Constants.GHZ_DAC_SERVER, getContext());

    // upload all memory and SRAM data
    for (FpgaModel fpga : expt.getFpgas()) {
      runRequest.add("Select Device", Data.valueOf(fpga.getName()));
      runRequest.add("Memory", Data.valueOf(fpga.getMemory()));
      if (fpga.hasDualBlockSram()) {
        runRequest.add("SRAM dual block",
            Data.valueOf(fpga.getSramDualBlock1()),
            Data.valueOf(fpga.getSramDualBlock2()),
            Data.valueOf(fpga.getSramDualBlockDelay()));
      } else {
        runRequest.add("SRAM Address", Data.valueOf(0L));
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

  @Setting(id = 1000,
           name = "Run",
           doc = "Runs the experiment and returns the timing data")
  public void run_experiment(long reps) throws InterruptedException, ExecutionException {
    Preconditions.checkArgument(reps > 0, "Reps must be a positive integer");
    Preconditions.checkArgument(reps % 30 == 0, "Reps must be a multiple of 30");
    
    if (configDirty || memDirty || sramDirty) {
      build_sequence();
    }
    
    // run in chunks of at most MAX_REPS
    List<Data> allData = Lists.newArrayList();
    long remaining = reps;
    while (remaining > 0) {
      long chunk = Math.min(remaining, Constants.MAX_REPS);
      remaining -= chunk;
      
      // set the number of reps
      nextRequest.getRecord(runIndex).getData().setWord(chunk, 0);
      
      Data data = getConnection().sendAndWait(nextRequest).get(runIndex);
      allData.add(data);
    }
    
    // put data together if it was run in multiple chunks
    if (allData.size() == 1) {
      lastData = allData.get(0);
    } else {
      int n = 0;
      int len = 0;
      for (Data data : allData) {
        int[] shape = data.getArrayShape();
        n = shape[0];
        len += shape[1];
      }
      Data collected = Data.ofType("*2w");
      collected.setArrayShape(n, len);
      int ofs = 0;
      for (Data data : allData) {
        int[] shape = data.getArrayShape();
        for (int i = 0; i < shape[0]; i++) {
          for (int j = 0; j < shape[1]; j++) {
            long val = data.get(i, j).getWord();
            collected.get(i, j+ofs).setWord(val);
          }
        }
        ofs += data.getArrayShape()[1];
      }
      lastData = collected;
    }
  }

  
  @Setting(id = 1100,
           name = "Get Data Raw",
           doc = "Gets the raw timing data from the previous run")
  @Returns("*2w")
  public Data get_data_raw() {
    return lastData;
  }
  @SettingOverload
  @Returns("*3w")
  public Data get_data_raw(int deinterlace) {
    long[][] raw = extractLastData();
    long[][][] reshaped = deinterlaceArray(raw, deinterlace);
    return Data.valueOf(reshaped);
  }

  
  @Setting(id = 1101,
          name = "Get Data Raw Microseconds",
          doc = "Gets the raw timing data from the previous run, converted to microseconds")
  @Returns("*2v[us]")
  public Data get_data_raw_microseconds() {
    double[][] ans = extractDataMicroseconds();
    return Data.valueOf(ans, "us");
  }
  @SettingOverload
  @Returns("*3v[us]")
  public Data get_data_raw_microseconds(int deinterlace) {
    double[][] ans = extractDataMicroseconds();
    double[][][] reshaped = deinterlaceArray(ans, deinterlace);
    return Data.valueOf(reshaped, "us");
  }
  
  
  @Setting(id = 1102,
      name = "Get Data Raw Switches",
      doc = "Gets the raw timing data from the previous run, converted to "
          + "booleans (T: switched, F: did not switch).")
  @Returns("*2b")
  public Data get_data_raw_switches() {
    boolean[][] switches = interpretSwitches();
    return Data.valueOf(switches);
  }
  @SettingOverload
  @Returns("*3b")
  public Data get_data_raw_switches(int deinterlace) {
    boolean[][][] switches = interpretSwitches(deinterlace);
    return Data.valueOf(switches);
  }
  
  
  @Setting(id = 1110,
           name = "Get Data Probs Separate",
           doc = "Get independent switching probabilities from the previous run."
               + "\n\n"
               + "Returns one probability for each timing channel, giving the switching "
               + "probability of that channel, independent of any other channels."
               + "\n\n"
               + "If only a subset of probabilities is required, you can pass a list "
               + "of qubits for which the probabilites should be returned.  The integers "
               + "must be in the range 0 to N-1, where N is the number of timing channels.")
  @Returns("*v")
  public Data get_data_probs_separate() {
    return Data.valueOf(getProbsSeparate());
  }

  @SettingOverload
  @Returns("*v")
  public Data get_data_probs_separate(long[] qubits) {
    double[] allProbs = getProbsSeparate();
    double[] desiredProbs = filterArray(allProbs, qubits);
    return Data.valueOf(desiredProbs);
  }
  
  @SettingOverload
  @Returns("*2v")
  public Data get_data_probs_separate(int deinterlace) {
    double[][] probs = getProbsSeparate(deinterlace);
    return Data.valueOf(probs);
  }
  
  @SettingOverload
  @Returns("*2v")
  public Data get_data_probs_separate(long[] states, int deinterlace) {
    double[][] probs = getProbsSeparate(deinterlace);
    for (int i = 0; i < probs.length; i++) {
      probs[i] = filterArray(probs[i], states);
    }
    return Data.valueOf(probs);
  }
  
  
  @Setting(id = 1111,
           name = "Get Data Probs",
           doc = "Get combined switching probabilities from the previous run."
               + "\n\n"
               + "Returns 2^N probabilities, where N is the number of timing channels "
               + "(i.e. the number of qubits).  The index i should be interpreted as "
               + "a binary integer with N bits, that is i=i[N-1..0]; then each number gives the "
               + "probability that the measured switching result was sw[0]=i[N-1], "
               + "sw[1]=i[N-2],..., sw[N-1]=i[0] (the zeroth switching result is in "
               + "the MSB of the index).  In other words, the answer returned is: "
               + "[P_00...00, P_00...01, P_00...10, P_00...11, ..., P_11...11], where "
               + "the bits in each index read from left to right refer to qubits "
               + "0, 1,..., N-1.  This convention was chosen to agree with what one "
               + "obtains when taking tensor products of qubit systems, and so this "
               + "makes for easier agreement with simulations."
               + "\n\n"
               + "If only a subset of probabilities is required, you can pass a list "
               + "of states for which the probabilites should be returned.  The integers "
               + "are interpreted in binary as described above.  For example, if you "
               + "only care about the null result (no switches), then you would pass [0].  "
               + "If on the other hand you are only measuring one qubit and only want P1 "
               + "to be returned, you should pass [1].")
  @Returns("*v")
  public Data get_data_probs() {
    return Data.valueOf(getProbs());
  }
  @SettingOverload
  @Returns("*v")
  public Data get_data_probs(long[] states) {
    double[] allProbs = getProbs();
    double[] desiredProbs = filterArray(allProbs, states);
    return Data.valueOf(desiredProbs);
  }
  @SettingOverload
  @Returns("*2v")
  public Data get_data_probs(int deinterlace) {
    double[][] probs = getProbs(deinterlace);
    return Data.valueOf(probs);
  }
  @SettingOverload
  @Returns("*2v")
  public Data get_data_probs(long[] states, int deinterlace) {
    double[][] probs = getProbs(deinterlace);
    for (int i = 0; i < probs.length; i++) {
      probs[i] = filterArray(probs[i], states);
    }
    return Data.valueOf(probs);
  }
  
  // filter an array 
  private double[] filterArray(double[] in, long[] indices) {
    double[] out = new double[indices.length];
    for (int i = 0; i < indices.length; i++) {
      out[i] = in[(int)indices[i]];
    }
    return out;
  }
  
  private boolean[][][] deinterlaceArray(boolean[][] in, int deinterlace) {
    int lim0 = deinterlace, lim1 = in.length, lim2 = in[0].length / deinterlace;
    boolean[][][] ans = new boolean[lim0][lim1][lim2];
    for (int i = 0; i < lim0; i++) {
      for (int j = 0; j < lim1; j++) {
        for (int k = 0; k < lim2; k++) {
          ans[i][j][k] = in[j][i+k*deinterlace];
        }
      }
    }
    return ans;
  }
  
  private long[][][] deinterlaceArray(long[][] in, int deinterlace) {
    int lim0 = deinterlace, lim1 = in.length, lim2 = in[0].length / deinterlace;
    long[][][] ans = new long[lim0][lim1][lim2];
    for (int i = 0; i < lim0; i++) {
      for (int j = 0; j < lim1; j++) {
        for (int k = 0; k < lim2; k++) {
          ans[i][j][k] = in[j][i+k*deinterlace];
        }
      }
    }
    return ans;
  }
  
  private double[][][] deinterlaceArray(double[][] in, int deinterlace) {
    int lim0 = deinterlace, lim1 = in.length, lim2 = in[0].length / deinterlace;
    double[][][] ans = new double[lim0][lim1][lim2];
    for (int i = 0; i < lim0; i++) {
      for (int j = 0; j < lim1; j++) {
        for (int k = 0; k < lim2; k++) {
          ans[i][j][k] = in[j][i+k*deinterlace];
        }
      }
    }
    return ans;
  }
  
  // extract data from last run as an array
  private long[][] extractLastData() {
    int[] shape = lastData.getArrayShape();
    long[][] ans = new long[shape[0]][shape[1]];
    for (int i = 0; i < shape[0]; i++) {
      for (int j = 0; j < shape[1]; j++) {
        ans[i][j] = lastData.get(i, j).getWord();
      }
    }
    return ans;
  }
  
  // convert data from last run to microseconds
  private double[][] extractDataMicroseconds() {
    long[][] raw = extractLastData();
    double[][] ans = new double[raw.length][];
    for (int i = 0; i < raw.length; i++) {
      ans[i] = FpgaModelBase.clocksToMicroseconds(raw[i]);
    }
    return ans;
  }
  
  
  // convert timing data to boolean switches, using the
  // specified switch intervals to interpret 0 and 1
  private boolean[][] interpretSwitches() {
    return interpretSwitches(1)[0];
  }
  private boolean[][][] interpretSwitches(int deinterlace) {
    List<PreampChannel> channels = getExperiment().getTimingChannels();
    long[][] clocks = extractLastData();
    boolean[][] switches = new boolean[clocks.length][];
    for (int i = 0; i < clocks.length; i++) {
      switches[i] = channels.get(i).interpretSwitches(clocks[i]);
    }
    return deinterlaceArray(switches, deinterlace);
  }
  

  // calculate separate switching probabilities, ie probabilities
  // for each channel to switch independent of the other channels
  private double[] getProbsSeparate() {
    return getProbsSeparate(1)[0];
  }
  private double[][] getProbsSeparate(int deinterlace) {
    boolean[][][] switches = interpretSwitches(deinterlace);
    double[][] probs = new double[deinterlace][];
    for (int i = 0; i < deinterlace; i++) {
      probs[i] = getProbsSeparateBase(switches[i]);
    }
    return probs;
  }
  private double[] getProbsSeparateBase(boolean[][] switches) {
    int N = switches.length;
    int reps = N > 0 ? switches[0].length : 0;
    
    double[] probs = new double[N];
    for (int i = 0; i < N; i++) {
      int count = 0;
      for (boolean sw : switches[i]) {
        count += sw ? 1 : 0;
      }
      probs[i] = (double)count / reps;
    }
    return probs;
  }

  
  // calculate combined state probabilities, ie probabilities for each
  // combination of switching states of the various timing channels
  private double[] getProbs() {
    return getProbs(1)[0];
  }
  private double[][] getProbs(int deinterlace) {
    boolean[][][] switches = interpretSwitches(deinterlace);
    double[][] probs = new double[deinterlace][];
    for (int i = 0; i < deinterlace; i++) {
      probs[i] = getProbsBase(switches[i]);
    }
    return probs;
  }
  private double[] getProbsBase(boolean[][] switches) {
    int N = switches.length;
    int reps = N > 0 ? switches[0].length : 0;
    
    // count switching states
    int[] counts = new int[1<<N];
    Arrays.fill(counts, 0);
    for (int j = 0; j < reps; j++) {
      int state = 0;
      for (int i = 0; i < N; i++) {
        state |= (switches[i][j] ? 1 : 0) << (N-1-i);
      }
      counts[state] += 1;
    }
    
    // convert counts to probabilities
    double[] probs = new double[counts.length];
    for (int i = 0; i < counts.length; i++) {
      probs[i] = (double)counts[i] / reps;
    }
    return probs;
  }
  

  //
  // diagnostic information
  //

  @Setting(id = 2001,
           name = "Dump Sequence Packet",
           doc = "Returns a dump of the packet to be sent to the GHz DACs server.")
  public Data dump_packet() {
    List<Data> records = Lists.newArrayList();
    for (Record r : nextRequest.getRecords()) {
      records.add(Data.clusterOf(Data.valueOf(r.getName()),
                                 r.getData()));
    }
    return Data.clusterOf(records);
  }

  /*
  @Setting(ID = 2002,
           name = "Dump Sequence Text",
           description = "Returns a dump of the current sequence in human-readable form")
  @Returns("*s*2s")
  public Data get_mem_text() {
    throw new RuntimeException("Not implemented yet.");
  }

  @Setting(ID = 2500,
           name = "Dump SRAM to data vault",
           description = "Send the current SRAM to the data vault")
  public void plot_sram(List<String> session, String name, boolean correct) {
    throw new RuntimeException("Not implemented yet.");
  }
  //*/
}
