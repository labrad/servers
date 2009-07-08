package org.labrad.qubits;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;

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
import org.labrad.qubits.channels.DeconvolvableSramChannel;
import org.labrad.qubits.channels.FastBiasChannel;
import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.channels.PacketResultHandler;
import org.labrad.qubits.channels.PreampChannel;
import org.labrad.qubits.channels.TriggerChannel;
import org.labrad.qubits.config.MicrowaveSourceConfig;
import org.labrad.qubits.config.SetupPacket;
import org.labrad.qubits.enums.BiasCommandType;
import org.labrad.qubits.mem.FastBiasCommands;
import org.labrad.qubits.mem.MemoryCommand;
import org.labrad.qubits.resources.MicrowaveSource;
import org.labrad.qubits.resources.Resources;
import org.labrad.qubits.templates.ExperimentBuilder;

import com.google.common.base.Preconditions;
import com.google.common.collect.ArrayListMultimap;
import com.google.common.collect.ListMultimap;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;


public class QubitContext extends AbstractServerContext {

	private ExperimentBuilder builder = null;
	private final Object builderLock = new Object();
	private Experiment expt = null;
	private Context setupContext = null;
	
	private Request nextRequest;
	private int dataIndex;
	
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
	private ExperimentBuilder getExperimentBuilder() {
		synchronized (builderLock) {
			Preconditions.checkNotNull(builder, "No sequence initialized in this context.");
			return builder;
		}
	}
	
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
		} else if (data.matchesType("ss")){
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
	
	//
	// Experiment
	//
	
	@Setting(id = 100,
			 name = "Initialize",
			 doc = "Initialize a new sequence with the given device and channel setup."
				 + "\n\n"
				 + "The setup can be specified in a number of different ways. "
				 + "If you specify a list of string names, devices with those names "
				 + "will be loaded from the standard registry location "
				 + "['', 'Servers', 'Qubit Server', 'Devices'].  You can alternately specify "
				 + "a second list of strings which will be used as aliases for those devices "
				 + "in this context."
				 + "\n\n"
				 //+ "The other possibility is to specify another context from which to copy "
				 //+ "the setup.  This will copy only the device and channel definitions, not "
				 //+ "any configuration, memory, or SRAM setup."
				 //+ "\n\n"
				 + "Finally, you can provide the device and channel definitions directly.  "
				 + "You do this by giving a list of devices, where each device is a cluster "
				 + "of name and channel list, and where each channel is a cluster of name "
				 + "and cluster of type and paramter list.")
    public void initialize(List<String> names) {
		// load devices from the registry
		initialize(names, names);
	}

	@SettingOverload
    public void initialize(List<String> names, List<String> aliases) {
		// load devices from the registry, but call them by different names
		Data template = Registry.loadDevices(names, aliases, getConnection(), getContext());
		initialize(template);
	}
	
	@SettingOverload
    public void initialize(long high, long low) {
		// copy the experiment defined in another context
		QubitContext ctx = (QubitContext)getServerContext(new Context(low, high));
		initialize(ctx.getExperimentBuilder());
	}
	
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
    	// turn the microwave source on , set the power level and frequency
    	IqChannel ch = getChannel(id, IqChannel.class);
    	ch.configMicrowavesOn(freq, power);
	}
    
    @SettingOverload
    public void config_microwaves(@Accepts({"s", "ss"}) Data id) {
    	// turn the microwave source off
    	IqChannel ch = getChannel(id, IqChannel.class);
    	ch.configMicrowavesOff();
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
    }

	@Setting(id = 230,
   		 	 name = "Config Settling",
             doc = "Configure the deconvolution settling rates for the given channel.")
    public void config_settling(@Accepts({"s", "ss"}) Data id,
    		                    @Accepts("*v[GHz]") double[] rates,
    		                    @Accepts("*v[GHz]") double[] amplitudes) {
    	AnalogChannel ch = getChannel(id, AnalogChannel.class);
    	ch.setSettling(rates, amplitudes);
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
			// TODO add sanity check on the packet structure
			packetList.add(packets.get(i));
		}
		getExperiment().setSetupState(states, packetList);
	}
	
	/*
    @Setting(ID = 280,
    		 name = "Config Timing Data",
    	     description = "Configure options for processing timing data before returning it.")
    public void config_timing_data(Data data) {
    	// cutoff, histogram, deinterlace, qubits together or separate
    	throw new RuntimeException("Not implemented yet.");
    }
    */
    
	
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
            	 + "If no final delay is specified, a default delay will be added "
            	 + "(currently 4.3 microseconds).")
    public void mem_bias(@Accepts({"*(s s v[mV])", "*((ss) s v[mV])"}) List<Data> commands) {
    	mem_bias(commands, Constants.DEFAULT_BIAS_DELAY);
    }
    
    @SettingOverload
    public void mem_bias(@Accepts({"*(s s v[mV])", "*((ss) s v[mV])"}) List<Data> commands,
    		             @Accepts("v[us]") double microseconds) {
    	// create a map with a list of commands for each board
    	ListMultimap<FpgaModel, MemoryCommand> fpgas = ArrayListMultimap.create();
    	
    	// parse the commands and group them for each fpga
    	for (Data cmd : commands) {
    		FastBiasChannel fb = getChannel(cmd.get(0), FastBiasChannel.class);
    		BiasCommandType type = BiasCommandType.fromString(cmd.get(1).getString());
    		double voltage = cmd.get(2).getValue();
    		FpgaModel fpga = fb.getFpgaModel();
    		fpgas.put(fpga, FastBiasCommands.get(type, fb, voltage));
    	}
    	
    	getExperiment().addBiasCommands(fpgas, microseconds);
    }
    
    
    @Setting(id = 320,
    		 name = "Mem Delay",
    		 doc = "Add a delay to all channels.")
    public void mem_delay(@Accepts("v[us]") double delay) {
    	getExperiment().addMemoryDelay(delay);
    }

    @Setting(id = 330,
   		     name = "Mem Call SRAM",
   		     doc = "Call the SRAM block specified by name."
   		    	 + "\n\n"
   		    	 + "The actual call will not be resolved until the sequence is run, "
   		    	 + "so the SRAM blocks do not have to be defined when this call is made."
   		    	 + "\n\n"
   		    	 + "If running a dual-block SRAM sequence, you must provide the names "
   		    	 + "of the first and second blocks, as well as a delay time between the "
   		    	 + "END of the first block and the START of the second block.  Note that "
   		    	 + "this delay will be rounded to the nearest integral number of nanoseconds "
   		    	 + "which may give unexpected results if the delay is converted from another "
   		    	 + "unit of time.")
    public void mem_call_sram(String block) {
    	getExperiment().callSramBlock(block);
    }
    
    @SettingOverload
    public void mem_call_sram(String block1, String block2, @Accepts("v[ns]") double delay) {
    	getExperiment().callSramDualBlock(block1, block2, delay);
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
    }

    
    //
    // SRAM
    //

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
   		    	 + "a multiple of 4, the data will be padded at the beginning "
   		    	 + "after deconvolution.")
    public void new_sram_block(String name, long length) {
    	getExperiment().startSramBlock(name, length);
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
    }
    
    @SettingOverload
    public void sram_iq_data(@Accepts({"s", "ss"}) Data id,
    		                 @Accepts("*c") Data vals,
    		                 boolean deconvolve) {
    	IqChannel ch = getChannel(id, IqChannel.class);
    	ComplexArray c = ComplexArray.fromData(vals);
    	ch.addData(new IqDataTime(c, !deconvolve));
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
    }
    
    @SettingOverload
    public void sram_analog_data(@Accepts({"s", "ss"}) Data id,
    		                     @Accepts("*v") Data vals,
    		                     boolean deconvolve) {
    	AnalogChannel ch = getChannel(id, AnalogChannel.class);
    	double[] arr = vals.getValueArray();
    	ch.addData(new AnalogDataTime(arr, !deconvolve));
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
    } 
    
    
    // triggers
    
    @Setting(id = 430,
    		 name = "SRAM Trigger Data",
    		 doc = "Set trigger data for the specified trigger channel")
    public void sram_trigger_data(@Accepts({"s", "ss"}) Data id,
    		                      @Accepts("*b") Data data) {
    	TriggerChannel ch = getChannel(id, TriggerChannel.class);
    	ch.addData(new TriggerDataTime(data.getBoolArray()));
    }

    @Setting(id = 431,
   		     name = "SRAM Trigger Pulses",
   		     doc = "Set trigger data as a series of pulses for the specified trigger channel")
    public void sram_trigger_pulses(@Accepts({"s", "ss"}) Data id,
    		                        @Accepts("*(v[ns] v[ns])") List<Data> pulses) {
    	TriggerChannel ch = getChannel(id, TriggerChannel.class);
    	for (Data pulse : pulses) {
    		int start = (int)pulse.get(0).getValue();
    		int length = (int)pulse.get(1).getValue();
    		ch.addPulse(start, length);
    	}
    }
    
    
    //
    // put the sequence together
    //
    
    @Setting(id = 900,
    		 name = "Build Sequence",
    		 doc = "Compiles SRAM and memory sequences into runnable form")
    public void build_sequence(long reps) throws InterruptedException, ExecutionException {
    	
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
    	
    	
    	//
    	// build setup packets
    	//
    	
    	// start with setup packets that have already been configured
    	List<Data> setupPackets = Lists.newArrayList(expt.getSetupPackets());
    	List<String> setupState = Lists.newArrayList(expt.getSetupState());
    	    	
    	// build setup packets for microwave sources
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
    	
    	// build a packet for the deconvolution server
    	Request deconvRequest = Request.to(Constants.DECONVOLUTION_SERVER);
    	List<PacketResultHandler> handlers = Lists.newArrayList();
    	for (DeconvolvableSramChannel ch : expt.getChannels(DeconvolvableSramChannel.class)) {
    		handlers.add(ch.requestDeconvolution(deconvRequest));
    	}
    	// send deconvolution request
    	List<Data> ans = getConnection().sendAndWait(deconvRequest);
    	// unpack deconvolved data and save it
    	for (PacketResultHandler handler : handlers) {
    		handler.handleResult(ans);
    	}
    	
    	
    	//
    	// build run packet
    	//
    	
    	Request runRequest = Request.to(Constants.GHZ_DAC_SERVER, getContext());
    	
    	// upload all memory and SRAM data
    	for (FpgaModel fpga : expt.getFpgas()) {
    		runRequest.add("Select Device", Data.valueOf(fpga.getName()));
    		if (fpga.hasSramChannels()) {
	    		if (fpga.hasDualBlockSram()) {
	    			runRequest.add("SRAM dual block",
	    					Data.clusterOf(
	    						Data.valueOf(fpga.getSramDualBlock1()),
	    						Data.valueOf(fpga.getSramDualBlock2()),
	    						Data.valueOf(fpga.getSramDualBlockDelay())));
	    		} else {
	    			runRequest.add("SRAM Address", Data.valueOf(0L));
	    			runRequest.add("SRAM", Data.valueOf(fpga.getSram()));
	    		}
    		}
    		runRequest.add("Memory", Data.valueOf(fpga.getMemory()));
    	}  
    	
    	// set up daisy chain and timing order
    	runRequest.add("Daisy Chain", Data.listOf(expt.getFpgaNames(), Setters.stringSetter));
    	runRequest.add("Timing Order", Data.listOf(expt.getTimingOrder(), Setters.stringSetter));

    	// run the sequence
    	Data sequenceArgs;
        if (setupPackets.size() == 0) {
    		sequenceArgs = Data.valueOf(reps);
    	} else {
    		sequenceArgs = Data.clusterOf(
    				Data.valueOf(reps),
    				Data.valueOf(true),
    				Data.clusterOf(setupPackets),
    				Data.listOf(setupState, Setters.stringSetter)
    		);
    	}
        dataIndex = runRequest.addRecord("Run Sequence", sequenceArgs);
    	nextRequest = runRequest;
    }
    
    @Setting(id = 1000,
   		     name = "Run",
   		     doc = "Runs the experiment and returns the timing data")
    @Returns("*2w")
    public Data run_experiment() throws InterruptedException, ExecutionException {
    	// TODO have a 'dirty bit' that gets checked to trigger a build if necessary
   	    return getConnection().sendAndWait(nextRequest).get(dataIndex);
    }
    
    //
    // diagnostic information
    //
    
    @Setting(id = 2001,
   		 name = "Dump Sequence Packet",
   		 doc = "Returns a representation of the packet to be sent to the GHz DACs server.")
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
    		 name = "Dump Sequence As Text",
    		 description = "Get a dump of the current sequence in human-readable form")
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
