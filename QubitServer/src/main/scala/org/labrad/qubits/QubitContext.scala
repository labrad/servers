package org.labrad.qubits

import org.labrad._
import org.labrad.annotations._
import org.labrad.data._
import org.labrad.qubits.channeldata._
import org.labrad.qubits.channels._
import org.labrad.qubits.config.MicrowaveSourceConfig
import org.labrad.qubits.config.MicrowaveSourceOffConfig
import org.labrad.qubits.enums.BiasCommandType
import org.labrad.qubits.enums.DacTriggerId
import org.labrad.qubits.mem.FastBiasCommands
import org.labrad.qubits.mem.MemoryCommand
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.resources.MicrowaveSource
import org.labrad.qubits.resources.Resources
import org.labrad.qubits.util.ComplexArray
import org.labrad.qubits.util.Grouping._
import org.labrad.types._
import scala.collection.mutable
import scala.concurrent.{Await, Future}
import scala.concurrent.duration._
import scala.reflect.ClassTag

class QubitContext(cxn: ServerConnection, resources: () => Resources) extends ServerContext {

  private implicit def executionContext = cxn.executionContext

  // The context in which we will create setup packets.
  // We make it different from our own context to avoid potential lockups due
  // to making recursive calls in a context.
  private val setupContext: Context = new Context(cxn.id, 1)

  private var expt: Experiment = null

  private var nextRequest: (Seq[(String, Data)], Array[Data], Array[String]) = null
  private var lastData: Data = null

  private var configDirty = true
  private var memDirty = true
  private var sramDirty = true

  /**
   * Initialize this context when it is first created.
   */
  override def init(): Unit = {}

  override def expire(): Unit = {}


  /**
   * Get the currently-defined experiment in this context.
   */
  private def getExperiment(): Experiment = {
    require(expt != null, "No sequence initialized in this context.")
    expt
  }

  /**
   * Set the current experiment in this context
   * @param expt
   */
  private def setExperiment(expt: Experiment): Unit = {
    this.expt = expt
  }


  type ChanId = Either[String, (String, String)]

  /**
   * Get a channel from the experiment that is of a particular Channel class
   * this unpacks the channel descriptor directly from the incoming LabRAD data
   */
  private def getChannel[T <: Channel : ClassTag](id: ChanId): T = {
    id match {
      case Left(device) => getChannel[T](device)
      case Right((device, channel)) => getChannel[T](device, channel)
    }
  }

  /**
   * Get a channel from the experiment that is of a particular Channel class
   * this unpacks the channel descriptor directly from the incoming LabRAD data
   */
  private def getChannel[T <: Channel : ClassTag](data: Data): T = {
    data match {
      case Str(device) => getChannel[T](device)
      case Cluster(Str(device), Str(channel)) => getChannel[T](device, channel)
      case data => sys.error(s"Unknown channel identifier: $data")
    }
  }

  /**
   * Get a channel from the experiment that is of a particular class
   */
  private def getChannel[T <: Channel : ClassTag](device: String, channel: String): T = {
    getExperiment().getDevice(device).getChannel[T](channel)
  }

  /**
   * Get a channel from the experiment that is of a particular class.
   * In this case, no channel name is specified, so this will succeed
   * only if there is a unique channel of the appropriate type.
   */
  private def getChannel[T <: Channel : ClassTag](device: String): T = {
    getExperiment().getDevice(device).getChannel[T]
  }

  /**
   * Build a setup packet from a given set of records, using the predefined setup context
   */
  private def buildSetupPacket(server: String, records: Data): Data = {
    Cluster(setupContext.toData, Str(server), records)
  }

  /**
   * Check the structure of a data object passed in as a setup packet
   */
  private def checkSetupPacket(packet: Data): Unit = {
    if (!Pattern("(ww)s?").accepts(packet.t)) {
      sys.error(s"Setup packet has invalid format: Expected ((ww) s ?{records}) but got ${packet.t}.")
    }
    val Cluster(_, _, records) = packet
    if (!records.isCluster) {
      sys.error(s"Setup packet has invalid format: Expected a cluster of records but got ${records.t}.")
    }
    for (i <- 0 until records.clusterSize) {
      val record = records(i)
      if (!Pattern("s?").accepts(record.t)) {
        sys.error(s"Setup packet has invalid format: Expected a cluster of (s{setting} ?{data}) for record $i but got ${record.t}")
      }
    }
  }

  //
  // Echo
  //
  @Setting(id = 99,
      name = "Echo",
      doc = "Echo back.")
  @Return("?")
  def echo(@Accept("?") packet: Data): Data = {
    packet
  }


  //
  // Experiment
  //

  type ChannelDef = (String, (String, Seq[String]))
  type DeviceDef = (String, Seq[ChannelDef])

  @Setting(id = 100,
      name = "Initialize",
      doc = """Initialize a new sequence with the given device and channel setup.
              |
              |Setup is given by a list of devices, where each device is a cluster
              |of name and channel list, and where each channel is a cluster of name
              |and cluster of type and parameter list.""")
  def initialize(@Accept("*(s{dev} *(s{chan} (s{type} *s{params})))") deviceDefs: Seq[DeviceDef]): Unit = {
    // get resources defined by wiring config
    val res = resources()

    // build experiment using the given device definitions
    val devs = deviceDefs.map { case (devName, channelDefs) =>
      val channels = channelDefs.map { case (chanName, (chanType, params)) =>
        Channel(chanName, chanType, params, res)
      }
      new Device(devName, channels)
    }
    val expt = new Experiment(devs)
    setExperiment(expt)
    expt.clearControllers()
  }


  //
  // Configuration
  //

  @Setting(id = 200,
      name = "New Config",
      doc = """Clear all config calls in this context.
              |
              |This clears all configuration from the config calls,
              |but leaves the device and channel setup unchanged.""")
  def new_config(): Unit = {
    getExperiment().clearConfig()
    configDirty = true
  }

  @Setting(id = 210,
      name = "Config Microwaves",
      doc = """Configure the Anritsu settings for the given channel.
              |
              |Note that if two microwave channels share the same source,
              |they must both use the same settings here.  If they do not,
              |an error will be thrown when you try to run the sequence.""")
  def config_microwaves(
      id: ChanId,
      @Accept("v[GHz]") freq: Double,
      @Accept("v[dBm]") power: Double
  ): Unit = {
    // turn the microwave source on, set the power level and frequency
    val ch = getChannel[IqChannel](id)
    ch.configMicrowavesOn(freq, power)
    configDirty = true
  }

  def config_microwaves(id: ChanId): Unit = {
    // turn the microwave source off
    val ch = getChannel[IqChannel](id)
    ch.configMicrowavesOff()
    configDirty = true
  }

  @Setting(id = 220,
      name = "Config Preamp",
      doc = """Configure the preamp settings for the given channel.
              |
              |This includes the DAC offset and polarity, as well as high-
              |and low-pass filtering.""")
  def config_preamp(id: ChanId,
      offset: Long, polarity: Boolean, highPass: String, lowPass: String): Unit = {
    // set the preamp offset, polarity and filtering options
    val ch = getChannel[PreampChannel](id)
    ch.setPreampConfig(offset, polarity, highPass, lowPass)
    configDirty = true
  }

  @Setting(id = 230,
      name = "Config Settling",
      doc = "Configure the deconvolution settling rates for the given channel.")
  def config_settling(
      id: ChanId,
      @Accept("*v[GHz]") rates: Array[Double],
      @Accept("*v[]") amplitudes: Array[Double]
  ): Unit = {
    val ch = getChannel[AnalogChannel](id)
    ch.setSettling(rates, amplitudes)
    configDirty = true
  }

  @Setting(id = 231,
      name = "Config Reflection",
      doc = "Configure the deconvolution reflection rates and amplitudes for the given channel.")
  def config_reflection(
      id: ChanId,
      @Accept("*v[GHz]") rates: Array[Double],
      @Accept("*v[]") amplitudes: Array[Double]
  ): Unit = {
    val ch = getChannel[AnalogChannel](id)
    ch.setReflection(rates, amplitudes)
    configDirty = true
  }

  @Setting(id = 240,
      name = "Config Timing Order",
      doc = """Configure the order in which timing results should be returned.
              |
              |If this option is not specified, timing results will be returned
              |for all timing channels in the order they were defined when this
              |sequence was initialized.""")
  def config_timing_order(@Accept("*s|*(ss)") ids: Seq[Data]): Unit = {
    val channels = Seq.newBuilder[TimingOrderItem]
    for (id <- ids) {
      def channelAndIndex(ch: String): (String, Int) = {
        ch.split("::") match {
          case Array(chanId, idxStr) => (chanId, idxStr.toInt)
          case Array(chanId) => (chanId, -1)
        }
      }
      val (timingChannel, idx) = if (id.isCluster) {
        val (dev, chanName) = id.get[(String, String)]
        val (chanId, idx) = channelAndIndex(chanName)
        (getChannel[TimingChannel](dev, chanId), idx)
      } else {
        val chanName = id.getString
        val (chanId, idx) = channelAndIndex(chanName)
        (getChannel[TimingChannel](chanId), idx)
      }
      channels += new TimingOrderItem(timingChannel, idx)
    }
    getExperiment().setTimingOrder(channels.result)
    configDirty = true
  }

  @Setting(id = 250,
      name = "Config Setup Packets",
      doc = """Configure other setup state and packets for this experiment.
              |
              |Setup information should be specified as a list of token strings
              |describing the state that should be setup before this sequence runs,
              |and a cluster of packets to be sent to initialize the other
              |servers into that state.  Each packet is a cluster of context (ww),
              |server name, and cluster of records, where each record is a cluster of
              |setting name and data.  These setup packets will get sent before
              |this sequence is run, allowing various sequences to be interleaved.""")
  def config_setup_packets(states: Seq[String], packets: Data): Unit = {
    val packetSeq = Seq.tabulate(packets.clusterSize) { i =>
      val packet = packets(i)
      checkSetupPacket(packet)
      packet
    }
    getExperiment().setSetupState(states, packetSeq)
    configDirty = true
  }

  @Setting(id = 260,
      name = "Config Autotrigger",
      doc = """Configure automatic inclusion of a trigger pulse on every SRAM sequence.
              |
              |Specifying a trigger channel name (e.g. 'S3') will cause a trigger pulse
              |to be automatically added to that channel on every board at the beginning of
              |every SRAM sequence.  This can be very helpful when viewing and debugging
              |SRAM output on the sampling scope, for example.
              |
              |You can also specify an optional length for the trigger pulse, which will
              |be rounded to the nearest ns.  If no length is specified, the default (16 ns)
              |will be used.""")
  def config_autotrigger(
      channel: String,
      @Accept("v[ns]") length: Double = Constants.AUTOTRIGGER_PULSE_LENGTH
  ): Unit = {
    getExperiment().setAutoTrigger(DacTriggerId.fromString(channel), length.toInt)
    configDirty = true
  }

  @Setting(id = 280,
      name = "Config Switch Intervals",
      doc = "Configure switching intervals for processing timing data from a particular timing channel.")
  def config_switch_intervals(
      id: ChanId,
      @Accept("*(v[us], v[us])") intervals: Array[(Double, Double)]
  ): Unit = {
    val channel = getChannel[PreampChannel](id)
    channel.setSwitchIntervals(intervals)
  }

  @Setting(id = 290,
      name = "Config Critical Phase",
      doc = "Configure the critical phases for processing ADC readout.")
  def config_critical_phases(
      id: ChanId,
      phase: Double
  ): Unit = {
    val channel = getChannel[AdcChannel](id)
    channel.setCriticalPhase(phase)
  }

  @Setting(id = 291,
      name = "Reverse Critical Phase Comparison",
      doc = """By default we do atan2(Q, I) > criticalPhase. Give this function
              |True and we do < instead (for this ADC channel).""")
  def reverse_critical_phase_comparison(
      id: ChanId,
      reverse: Boolean
  ): Unit = {
    val channel = getChannel[AdcChannel](id)
    channel.reverseCriticalPhase(reverse)
  }

  @Setting(id = 292,
      name = "Set IQ Offsets",
      doc = "Bother Dan")
  def set_iq_offset(
      id: ChanId,
      offsets: (Int, Int)
  ): Unit = {
    val channel = getChannel[AdcChannel](id)
    channel.setIqOffset(offsets._1, offsets._2)
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
  def new_mem(): Unit = {
    getExperiment().clearControllers()
    memDirty = true
  }

  /**
   * Add bias commands in parallel to the specified channels
   * @param commands
   * @param microseconds
   */
  @Setting(id = 310,
      name = "Mem Bias",
      doc = """Adds Bias box commands to the specified channels.
              |
              |Each bias command is specified as a cluster of channel, command
              |name, and voltage level.  As for other settings, the channel can
              |be specified as either a device name, or a (device, channel) cluster,
              |where the first option is allowed only when there is no ambiguity,
              |that is, when there is only one bias channel for the device.
              |
              |The command name specifies which DAC and mode are to be used for this
              |bias command.  Allowed values are 'dac0', 'dac0noselect', 'dac1', and 'dac1slow'.
              |See the FastBias documentation for information about these options.
              |
              |A final delay can be specified to have a delay command added after the bias
              |commands on all memory sequences.  If no final delay is specified, a default
              |delay will be added (currently 4.3 microseconds).""")
  def mem_bias(
      @Accept("*(s s v[mV]) | *((ss) s v[mV])") commands: Seq[(Data, String, Double)],
      @Accept("v[us]") microseconds: Double = Constants.DEFAULT_BIAS_DELAY
  ): Unit = {
    // parse the commands and find the board they apply to
    val boardsAndCommands = commands.map { case (id, cmdTypeName, voltage) =>
      val ch = getChannel[FastBiasFpgaChannel](id)
      val cmdType = BiasCommandType.fromString(cmdTypeName)
      (ch.getFpgaModel(), FastBiasCommands.get(cmdType, ch, voltage))
    }

    // group commands by fpga board
    val fpgas = boardsAndCommands
      .groupBy { case (board, cmd) => board }
      .map { case (board, cmds) => board -> cmds.map(_._2) } // just keep cmd from board, command tuple

    getExperiment().addBiasCommands(fpgas, microseconds)
    memDirty = true
  }

  @Setting(id = 320,
      name = "Mem Delay",
      doc = "Add a delay to all channels.")
  def mem_delay(@Accept("v[us]") delay: Double): Unit = {
    getExperiment().addMemoryDelay(delay)
    memDirty = true
  }

  @Setting(id = 321,
    name = "Mem Delay Single",
    doc = "Add a delay to a single channel.")
  def mem_delay_single(@Accept("(s v[us]) | ((ss) v[us])") command: Data): Unit = {
    val ch = getChannel[FastBiasFpgaChannel](command(0))
    val delay_us = command(1).getValue
    getExperiment().addSingleMemoryDelay(ch.getFpgaModel(), delay_us)
    memDirty = true
  }

  @Setting(id = 330,
      name = "Mem Call SRAM",
      doc = """Call the SRAM block specified by name.
              |
              |The actual call will not be resolved until the sequence is run,
              |so the SRAM blocks do not have to be defined when this call is made.
              |
              |If running a dual-block SRAM sequence, you must provide the names
              |of the first and second blocks (the delay between the END of the first block
              |and the START of the second block must be specified separately).""")
  def mem_call_sram(block: String): Unit = {
    getExperiment().callSramBlock(block)
    memDirty = true
  }

  def mem_call_sram(block1: String, block2: String) {
    getExperiment().callSramDualBlock(block1, block2)
    memDirty = true
  }

  @Setting(id = 340,
      name = "Mem Start Timer",
      doc = "Start the timer for the specified timing channels.")
  def mem_start_timer(@Accept("*s | *(ss)") ids: Seq[Data]): Unit = {
    val channels = ids.map { id => getChannel[PreampChannel](id) }
    getExperiment().startTimer(channels)
    memDirty = true
  }

  @Setting(id = 350,
      name = "Mem Stop Timer",
      doc = "Stop the timer for the specified timing channels.")
  def mem_stop_timer(@Accept("*s | *(ss)") ids: Seq[Data]): Unit = {
    val channels = ids.map { id => getChannel[PreampChannel](id) }
    getExperiment().stopTimer(channels)
    memDirty = true
  }

  @Setting(id = 360,
      name = "Mem Sync Delay",
      doc = "Adds a memory delay to synchronize all channels.  Call last in the memory sequence.")
  def mem_sync_delay(): Unit = {
    getExperiment().addMemSyncDelay()
    memDirty = true
  }

  //
  // DC Rack FastBias
  //

  @Setting(id = 365,
      name = "Config Bias Voltage",
      doc = "Set the bias for this fastBias card (controlled by the DC rack server, over serial)")
  def config_bias_voltage(
      id: ChanId,
      dac: String,
      @Accept("v[V]") voltage: Double
  ): Unit = {
    // TODO: create a mem_bias call if the channel is a FastBiasFpga channel.
    val ch = getChannel[FastBiasSerialChannel](id)
    ch.configBias(dac, voltage)
  }

  @Setting(id = 366,
      name = "Config loop delay",
      doc = "Set the delay between stats. This used to be called 'biasOperateSettling'.")
  def config_loop_delay(@Accept("v[us]") loopDelay: Double): Unit = {
    getExperiment.configLoopDelay(loopDelay)
  }


  //
  // Jump Table
  //

  @Setting(id = 371,
      name = "Jump Table Add Entry",
      doc = "Add a jump table entry to a single board.")
  def jump_table_add_entry(
      commandName: String,
      @Accept("w{NOP,END} | ww{IDLE} | www{JUMP} | wwww{CYCLE}") commandData: Data
  ): Unit = {
    getExperiment.addJumpTableEntry(commandName, commandData)
  }


  //
  // SRAM
  //

  /**
   * Start a new named SRAM block.
   */
  @Setting(id = 400,
      name = "New SRAM Block",
      doc = """Create a new SRAM block with the specified name and length, for this channel.
              |
              |All subsequent SRAM calls will affect this block, until a new block
              |is created.  If you do not provide SRAM data for a particular channel,
              |it will be filled with zeros (and deconvolved).  If the length is not
              |a multiple of 4, the data will be padded at the beginning after
              |deconvolution.""")
  def new_sram_block(name: String, length: Long, @Accept("ss") id: Data): Unit = {
    val ch = getChannel[SramChannelBase[_]](id)
    ch.getFpgaModel().startSramBlock(name, length)
    ch.setCurrentBlock(name)
    sramDirty = true
  }

  @Setting(id = 401,
      name = "SRAM Dual Block Delay",
      doc = """Set the delay between the first and second blocks of a dual-block SRAM command.
              |
              |Note that if dual-block SRAM is used in a given sequence, there can only be one
              |such call, so that this command sets the delay regardless of the block names.
              |Also note that this delay will be rounded to the nearest integral number of
              |nanoseconds which may give unexpected results if the delay is converted from
              |another unit of time.""")
  def sram_dual_block_delay(@Accept("v[ns]") delay: Double): Unit = {
    getExperiment().setSramDualBlockDelay(delay)
    sramDirty = true
  }


  /**
   * Add SRAM data for a microwave IQ channel.
   */
  @Setting(id = 410,
      name = "SRAM IQ Data",
      doc = """Set IQ data for the specified channel.
              |
              |The data is specified as a list of complex numbers,
              |with the real and imaginary parts giving the I and Q
              |microwave quadratures.  The length of the data should
              |match the length of the current SRAM block.
              |An optional boolean specifies whether the data
              |should be deconvolved (default: true).
              |If deconvolve=false, the data can be specified as DAC-ready
              |I and Q integers.
              |If zeroEnds=true (default: true), then the first and last
              |4 nanoseconds of the deconvolved sequence will be set to the
              |deconvolved zero value, to ensure microwaves are turned off.""")
  def sram_iq_data(
      id: ChanId,
      @Accept("*c | (*i{I}, *i{Q})") vals: Data,
      deconvolve: Boolean = true,
      zeroEnds: Boolean = true
  ): Unit = {
    val ch = getChannel[IqChannel](id)
    if (vals.isCluster) {
      require(!deconvolve, "Must not deconvolve if providing DAC'ified IQ data.")
      val (is, qs) = vals.get[(Array[Int], Array[Int])]
      ch.addData(new IqDataTimeDacified(is, qs))
    } else {
      val c = ComplexArray.fromData(vals)
      ch.addData(new IqDataTime(c, !deconvolve, zeroEnds))
    }
    sramDirty = true
  }


  /**
   * Add SRAM data for a microwave IQ channel in Fourier representation.
   */
  @Setting(id = 411,
      name = "SRAM IQ Data Fourier",
      doc = """Set IQ data in Fourier representation for the specified channel.
              |
              |The data is specified as a list of complex numbers,
              |with the real and imaginary parts giving the I and Q
              |microwave quadratures.  The length of the data should
              |match the length of the current SRAM block.
              |If zeroEnds=true (default: true), then the first and last
              |4 nanoseconds of the deconvolved sequence will be set to the
              |deconvolved zero value, to ensure microwaves are turned off.""")
  def sram_iq_data_fourier(
      id: ChanId,
      @Accept("*c") vals: Data,
      @Accept("v[ns]") t0: Double,
      zeroEnds: Boolean = true
  ): Unit = {
    val ch = getChannel[IqChannel](id)
    val c = ComplexArray.fromData(vals)
    ch.addData(new IqDataFourier(c, t0, zeroEnds))
    sramDirty = true
  }


  /**
   * Add SRAM data for an analog channel
   */
  @Setting(id = 420,
      name = "SRAM Analog Data",
      doc = """Set analog data for the specified channel.
              |
              |The length of the data should match the length of the
              |current SRAM block.  An optional boolean specifies
              |whether the data should be deconvolved (default: true).
              |If deconvolve=false, the data can be supplied as DAC-ready
              |integers.
              |If averageEnds=true (default: true), then the first and last
              |4 nanoseconds of the deconvolved sequence will be averaged and
              |set to the same value, to ensure the DAC outputs a constant
              |after the sequence is run.
              |If dither=true (default: false), then the deconvolved data
              |will be dithered by adding random noise to reduce quantization
              |noise (see http://en.wikipedia.org/wiki/Dither).""")
  def sram_analog_data(
      id: ChanId,
      @Accept("*v | *i") vals: Either[Array[Double], Array[Int]],
      deconvolve: Boolean = true,
      averageEnds: Boolean = true,
      dither: Boolean = false
  ): Unit = {
    val ch = getChannel[AnalogChannel](id)
    vals match {
      case Left(vals) =>
        ch.addData(new AnalogDataTime(vals, !deconvolve, averageEnds, dither))

      case Right(ints) =>
        require(!deconvolve, "Must not deconvolve if providing DAC'ified data.")
        ch.addData(new AnalogDataTimeDacified(ints))
    }
    sramDirty = true
  }


  /**
   * Add SRAM data for an analog channel in Fourier representation
   */
  @Setting(id = 421,
      name = "SRAM Analog Data Fourier",
      doc = """Set analog data in Fourier representation for the specified channel.
              |
              |Because this represents real data, we only need half as many samples.
              |In particular, for a sequence of length n, the fourier data given
              |here must have length n/2+1 (n even) or (n+1)/2 (n odd).
              |If averageEnds=true (default: true), then the first and last
              |4 nanoseconds of the deconvolved sequence will be averaged and
              |set to the same value, to ensure the DAC outputs a constant
              |after the sequence is run.
              |If dither=true (default: false), then the deconvolved data
              |will be dithered by adding random noise to reduce quantization
              |noise (see http://en.wikipedia.org/wiki/Dither).""")
  def sram_analog_fourier_data(
      id: ChanId,
      @Accept("*c") vals: Data,
      @Accept("v[ns]") t0: Double,
      averageEnds: Boolean = true,
      dither: Boolean = false
  ): Unit = {
    val ch = getChannel[AnalogChannel](id)
    val c = ComplexArray.fromData(vals)
    ch.addData(new AnalogDataFourier(c, t0, averageEnds, dither))
    sramDirty = true
  }


  // triggers

  @Setting(id = 430,
      name = "SRAM Trigger Data",
      doc = "Set trigger data for the specified trigger channel")
  def sram_trigger_data(
      id: ChanId,
      data: Array[Boolean]
  ): Unit = {
    val ch = getChannel[TriggerChannel](id)
    ch.addData(new TriggerDataTime(data))
    sramDirty = true
  }

  @Setting(id = 431,
      name = "SRAM Trigger Pulses",
      doc = """Set trigger data as a series of pulses for the specified trigger channel
              |
              |Each pulse is given as a cluster of (start, length) values,
              |specified in nanoseconds.""")
  def sram_trigger_pulses(
      id: ChanId,
      @Accept("*(v[ns] v[ns])") pulses: Seq[(Double, Double)]
  ): Unit = {
    val ch = getChannel[TriggerChannel](id)
    for ((start, length) <- pulses) {
      ch.addPulse(start.toInt, length.toInt)
    }
    sramDirty = true
  }

  //
  // ADC settings
  //

  @Setting(id = 510,
      name = "Set Start Delay",
      doc = """Sets the SRAM start delay for this channel; valid for ADC, IQ, and analog channels.
              |
              |First argument {s or (ss)}: channel (either device name or (device name, channel name)
              |Second: delay, in clock cycles (typically 4 ns) (w)""")
  def adc_set_start_delay(
      id: ChanId,
      delay: Int
  ): Unit = {
    val ch = getChannel[StartDelayChannel](id)
    ch.setStartDelay(delay)
  }

  @Setting(id = 520,
      name = "ADC Set Mode",
      doc = """Sets the mode of this channel.
              |
              |First argument {s or (ss)}: channel (either device name or (device name, channel name)
              |Second {s or (si)}: either 'demodulate' or ('average', [demod channel number])""")
  def adc_set_mode(
      id: ChanId,
      @Accept("s|si") mode: Data
  ): Unit = {
    val ch = getChannel[AdcChannel](id)
    if (mode.isString) {
      ch.setToAverage()
    } else {
      ch.setToDemodulate(mode(1).getInt)
    }
  }

  @Setting(id = 530,
      name = "ADC Set Filter Function",
      doc = """Sets the filter function for this channel; must be an adc channel in demod mode.
              |
              |First argument {s or (ss)}: channel (either device name or (device name, channel name)
              |Second {s}: the filter function, represented as a string
              |Third {w}: the length of the stretch
              |Fourth {w}: the index at which to stretch""")
  def adc_set_filter_function(
      id: ChanId,
      bytes: String,
      stretchLen: Long,
      stretchAt: Long
  ): Unit = {
    val ch = getChannel[AdcChannel](id)
    ch.setFilterFunction(bytes, stretchLen.toInt, stretchAt.toInt)
  }

  @Setting(id = 531,
      name = "ADC Set Trig Magnitude",
      doc = """Sets the filter function for this channel.
              |
              |Must be an adc channel in demod mode and the sub-channel must be valid (i.e. under 4 for build 1).
              |sineAmp and cosineAmp range from 0 to 255.
              |First argument {s or (ss)}: channel (either device name or (device name, channel name)
              |Second {w}: sine amplitude
              |Third {w}: cosine amplitude""")
  def adc_set_trig_magnitude(
      id: ChanId,
      sineAmp: Long,
      cosineAmp: Long
  ): Unit = {
    val ch = getChannel[AdcChannel](id)
    ch.setTrigMagnitude(sineAmp.toInt, cosineAmp.toInt)
  }

  @Setting(id = 532,
      name = "ADC Demod Phase",
      doc = """Sets the demodulation phase.
              |
              |Must be an adc channel in demod mode.
              |See the documentation for this in the GHz FPGA server.
              |First argument {s or (ss)}: channel (either device name or (device name, channel name)
              |Second {(i,i) or (v[Hz], v[rad])}: (dPhi, phi0) or (frequency (Hz), offset (radians))""")
  def adc_demod_phase(
      id: ChanId,
      @Accept("ii | v[Hz]v[rad]") dat: Data
  ): Unit = {
    val ch = getChannel[AdcChannel](id)
    if (dat.t == Type("ii")) {
      ch.setPhase(dat(0).getInt, dat(1).getInt)
    } else {
      ch.setPhase(dat(0).getValue, dat(1).getValue)
    }
  }

  @Setting(id = 533, name = "ADC Trigger Table",
      doc = """Pass through to GHz FPGA server's ADC Trigger Table.
              |
              |data: List of (count,delay,length,rchan) tuples.""")
  def adc_trigger_table(
      id: ChanId,
      @Accept("*(i,i,i,i)") data: Data
  ): Unit = {
    val ch = getChannel[AdcChannel](id)
    ch.setTriggerTable(data)
  }

  @Setting(id = 534, name = "ADC Mixer Table",
      doc = """Pass through to GHz FPGA server's ADC Mixer Table.
              |
              |data: List of (count,delay,length,rchan) tuples.""")
  def adc_mixer_table(
      id: ChanId,
      @Accept("*2i {Nx2 array of IQ values}") data: Data
  ): Unit = {
    val ch = getChannel[AdcChannel](id)
    ch.setMixerTable(data)
  }

  //
  // put the sequence together
  //

  @Setting(id = 900,
      name = "Build Sequence",
      doc = """Compiles SRAM and memory sequences into runnable form.
              |
              |Any problems with the setup (for example, conflicting microwave
              |settings for two channels that use the same microwave source)
              |will be detected at this point and cause an error to be thrown.""")
  def build_sequence(): Unit = {

    val expt = getExperiment()

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

    // Check microwave source configuration.
    //
    // We group the IQ channels by the microwave source they use and check that
    // all channels sharing a particular source agree on its configuration. For
    // any microwave boards which are not being used by IQ channels, we
    // configure their sources to be off.

    val uwaveConfigs = mutable.Map.empty[MicrowaveSource, MicrowaveSourceConfig]

    val configsBySrc = (for {
      dev <- expt.devices
      chan <- dev.getChannels[IqChannel]
    } yield {
      val src = chan.getMicrowaveSource()
      val config = chan.getMicrowaveConfig()
      require(config != null, s"No microwaves configured: dev=${dev.name}, channel=${chan.name}")
      src -> (dev, chan, config)
    }).groupByKeyValue

    for ((src, chansAndConfigs) <- configsBySrc) {
      val configs = chansAndConfigs.map { case (dev, chan, config) => config }.toSet.toSeq
      require(configs.size == 1, {
        val lines = Seq.newBuilder[String]
        lines += s"Conflicting microwave configurations for source '${src.name}'"
        for ((dev, chan, config) <- chansAndConfigs) {
          lines += s"  dev=${dev.name}, channel=${chan.name}: $config"
        }
        lines.result.mkString("\n")
      })
      uwaveConfigs(src) = configs(0)
    }

    for (fpga <- getExperiment().getMicrowaveFpgas()) {
      val src = fpga.getMicrowaveSource()
      if (!uwaveConfigs.contains(src)) {
        uwaveConfigs(src) = MicrowaveSourceOffConfig
      }
    }


    //
    // build setup packets
    //

    val setupPackets = Array.newBuilder[Data]
    val setupState = Array.newBuilder[String]

    // start with setup packets that have already been configured
    setupPackets ++= expt.getSetupPackets()
    setupState ++= expt.getSetupState()

    // build setup packets for microwave sources
    // TODO if a microwave source is used for dummy channels and real channels, resolve here
    val anritsuFuture = cxn.send(Constants.ANRITSU_SERVER, "List Devices" -> Data.NONE)
    val hittiteFuture = cxn.send(Constants.HITTITE_SERVER, "List Devices" -> Data.NONE)

    val anritsuList = Await.result(anritsuFuture, 30.seconds)(0).get[Seq[(Long, String)]]
    val anritsuNames = anritsuList.map(_._2).toSet

    val hittiteList = Await.result(hittiteFuture, 30.seconds)(0).get[Seq[(Long, String)]]
    val hittiteNames = hittiteList.map(_._2).toSet

    for ((src, config) <- uwaveConfigs) {
      val p = config.getSetupPacket(src)
      val devName = src.name
      if (anritsuNames.contains(devName)) {
        setupPackets += buildSetupPacket(Constants.ANRITSU_SERVER, p.recordData)
      } else if (hittiteNames.contains(devName)) {
        setupPackets += buildSetupPacket(Constants.HITTITE_SERVER, p.recordData)
      } else {
        sys.error(s"Microwave device not found: '$devName'")
      }

      setupState += p.state
    }

    // build setup packets for preamp boards
    // TODO improve DC Racks server (e.g. need caching)
    for (ch <- expt.getChannels[PreampChannel]) {
      if (ch.hasPreampConfig()) {
        val p = ch.getPreampConfig().getSetupPacket(ch)
        setupPackets += buildSetupPacket(Constants.DC_RACK_SERVER, p.recordData)
        setupState += p.state
      }
    }

    for (ch <- expt.getChannels[FastBiasSerialChannel]) {
      if (ch.hasSetupPacket()) {
        val p = ch.getSetupPacket()
        setupPackets += buildSetupPacket(Constants.DC_RACK_SERVER, p.recordData)
        setupState += p.state
      }
    }


    // System.out.println("starting deconv");

    //
    // deconvolve SRAM sequences
    //

    // this is the new-style deconvolution routine which sends all deconvolution requests in separate packets
    val deconvolver = new DeconvolutionProxy(cxn)
    val deconvolutions = for {
      fpga <- expt.getDacFpgas.toSeq
      if fpga.hasSramChannel
    } yield fpga.deconvolveSram(deconvolver)

    Await.result(Future.sequence(deconvolutions), 1.minute)

    //
    // build run packet
    //

    val runRequest = mutable.Buffer.empty[(String, Data)]

    // NEW 4/22/2011 - pomalley
    // settings for ADCs
    for (fpga <- expt.getAdcFpgas()) {
      runRequest += "Select Device" -> Str(fpga.name)
      runRequest ++= fpga.packets
    }

    // upload all memory and SRAM data
    for (fpga <- expt.getDacFpgas()) {
      runRequest ++= fpga.packets
      if (getExperiment().isLoopDelayConfigured()) {
        runRequest += "Loop Delay" -> Value(expt.getLoopDelay(), "us")
      }
    }

    // set up daisy chain and timing order
    runRequest += "Daisy Chain" -> Arr(expt.getFpgaNames().toArray)
    runRequest += "Timing Order" -> Arr(expt.getTimingOrder().toArray)

    // run the sequence
    nextRequest = (runRequest, setupPackets.result, setupState.result)


    // clear the dirty bits
    configDirty = false
    memDirty = false
    sramDirty = false
  }

  @Setting(id = 1009,
      name = "Get SRAM Final",
      doc = "Make sure to run build sequence first.")
  @Return("*w")
  def get_sram_final(@Accept("s|ss") id: Data): Array[Long] = {
    val iq = getChannel[IqChannel](id)
    iq.getFpgaModel().getSram()
  }

  @Setting(id = 1000,
      name = "Run",
      doc = """Runs the current sequence by sending to the GHz DACs server.
              |
              |Note that no timing data are returned here.  You must call one or more
              |of the 'Get Data *' methods to retrieve the data in the desired format.""")
  def run_experiment(reps: Long): Unit = {
    require(reps > 0, "Reps must be a positive integer")
    if (configDirty || memDirty || sramDirty) {
      build_sequence()
    }
    val (records, setupPackets, setupState) = nextRequest
    val allRecords = records :+ ("Run Sequence" -> Cluster(
      UInt(reps),
      Bool(true), // return timing results
      Cluster(setupPackets: _*),
      Arr(setupState)
    ))
    val f = cxn.send(Constants.GHZ_FPGA_SERVER, allRecords: _*)
    lastData = Await.result(f, 10.minutes).last
  }

  @Setting(id = 1001,
      name = "Run DAC SRAM",
      doc = """Similar to 'Run', but does dac_run_sram instead of run_sequence.
              |
              |This simply runs the DAC SRAM (once or repeatedly) and gives
              |no data back. Used to determine the power output, etc.""")
  def run_dac_sram(
      @Accept("*w") data: Data,
      @Accept("b") loop: Boolean
  ): Unit = {
    if (configDirty || memDirty || sramDirty) {
      build_sequence()
    }

    // change the run request to dac_run_sram request
    val (records, setupPackets, setupState) = nextRequest
    val allRecords = records :+ ("DAC Run SRAM" -> Cluster(data, Bool(loop)))
    val f = cxn.send(Constants.GHZ_FPGA_SERVER, allRecords: _*)
    Await.result(f, 10.minutes)
  }

  @Setting(id = 1002,
      name = "ADC Run Demod",
      doc = "Builds the sequence and runs ADC Run Demod")
  @Return("*3i{I,Q}, *i{pktCounters}, *i{readbackCounters}")
  def adc_run_demod(@Accept("s") mode: String = "iq"): Data = {
    if (configDirty || memDirty || sramDirty) {
      build_sequence()
    }
    val (records, setupPackets, setupState) = nextRequest
    val allRecords = records :+ ("ADC Run Demod" -> Str(mode))
    val f = cxn.send(Constants.GHZ_FPGA_SERVER, allRecords: _*)
    Await.result(f, 10.minutes).last
  }

  @Setting(id = 1100,
      name = "Get Data Raw",
      doc = """Get the raw timing data from the previous run.
              |
              |The returned data is a 4 index array. The meanings of the indices
              |are (channel, stat, demod, IQ):
              |  channel: Which ADC channel. Usually this corresponds to a
              |    single qubit.
              |  stat: Which repetition of the pulse sequence.
              |  demod: Which ADC demod (a.k.a. retrigger).
              |  IQ : Index over I and Q. This axis is always length 2.
              |
              |Given a deinterlace argument, only DAC data are returned.""")
  @Return("*4i")
  def get_data_raw(): Data = {
    lastData
  }

  @Setting(id = 1112,
      name = "Get Data Raw Phases",
      doc = "Gets the raw data from the ADC results, converted to phases.")
  @Return("*3v[rad]")
  def get_data_raw_phases(): Data = {
    val ans = extractDataPhases()

    val builder = DataBuilder("*3v[rad]")
    builder.array(ans.length, ans(0).length, ans(0)(0).length)
    for (a <- ans; b <- a; c <- b) {
      builder.value(c)
    }
    builder.result()
  }

  private def extractDataPhases(): Array[Array[Array[Double]]] = {
    val shape = lastData.arrayShape
    val ans = Array.ofDim[Array[Double]](shape(0), shape(1))
    val adcIndices = this.getExperiment().adcTimingOrderIndices()
    val timingChannels = getExperiment().getTimingChannels()

    for (whichAdcChannel <- 0 until shape(0)) {
      val ch = timingChannels(adcIndices(whichAdcChannel)).getChannel().asInstanceOf[AdcChannel]
      for (j <- 0 until shape(1)) {
        ans(whichAdcChannel)(j) = ch.getPhases(
          lastData(whichAdcChannel, j, 0).get[Array[Int]],
          lastData(whichAdcChannel, j, 1).get[Array[Int]]
        )
      }
    }
    ans
  }

  //
  // diagnostic information
  //

  @Setting(id = 2001,
      name = "Dump Sequence Packet",
      doc = """Returns a dump of the packet to be sent to the GHz DACs server.
              |
              |The packet dump is a cluster of records where each record is itself
              |a cluster of (name, data).  For a human-readable dump of the packet,
              |see the 'Dump Sequence Text' setting.""")
  def dump_packet(): Data = {
    val (records, setupPackets, setupState) = nextRequest
    val recordData = records.map { case (name, data) =>
      Cluster(Str(name), data)
    }
    Cluster(recordData: _*)
  }

  @Setting(id = 2002,
      name = "Dump Sequence Text",
      doc = "Returns a dump of the current sequence in human-readable form")
  @Return("s")
  def dump_text(): String = {

    val (records, setupPackets, setupState) = nextRequest

    val deviceNamesBuilder = Set.newBuilder[String]
    val memorySequences = mutable.Map.empty[String, Array[Long]]
    val sramSequences = mutable.Map.empty[String, Array[Long]]
    val commands = mutable.Buffer.empty[(String, Data)]

    // iterate over packet, pulling out commands
    var currentDevice: String = null
    for ((name, data) <- records) {
      name match {
        case "Select Device" =>
          currentDevice = data.getString
          deviceNamesBuilder += currentDevice

        case "Memory" =>
          memorySequences(currentDevice) = data.get[Array[Long]]

        case "SRAM" =>
          sramSequences(currentDevice) = data.get[Array[Long]]

        case "SRAM Address" =>
          // do nothing

        case _ =>
          commands += name -> data
      }
    }
    val deviceNames = deviceNamesBuilder.result.toSeq.sorted

    val lines = Seq.newBuilder[String]

    val devLine = new StringBuilder()
    for (dev <- deviceNames) {
      devLine.append(dev)
      devLine.append(", ")
    }
    lines += devLine.toString()
    lines += ""

    lines += "Memory"
    if (deviceNames.size > 0) {
      val N = memorySequences(deviceNames(0)).length
      for (i <- 0 until N) {
        val row = new StringBuilder()
        for (name <- deviceNames) {
          row.append("%06X".format(memorySequences(name)(i)))
          row.append("  ")
        }
        lines += row.toString()
      }
    }
    lines += ""

    lines += "SRAM"
    if (deviceNames.size > 0) {
      val N = sramSequences(deviceNames(0)).length
      for (i <- 0 until N) {
        val row = new StringBuilder()
        for (name <- deviceNames) {
          row.append("%08X".format(sramSequences(name)(i)))
          row.append("  ")
        }
        lines += row.toString()
      }
    }
    lines += ""

    for ((name, data) <- commands) {
      lines += name
      lines += data.toString
      lines += ""
    }

    lines += "Setup Packets"
    for ((packet, state) <- setupPackets zip setupState) {
      lines += "state: " + state
      lines += "packet: " + packet
      lines += ""
    }

    val result = new StringBuilder()
    for (line <- lines.result) {
      result ++= line
      result += '\n'
    }
    result.toString
  }
}
