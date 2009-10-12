package org.labrad.qubits;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

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
import org.labrad.qubits.resources.DacBoard;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;
import com.google.common.collect.Maps;

public abstract class FpgaModelBase implements FpgaModel {
		
	public final static double FREQUENCY = 25.0;
	
	private DacBoard dacBoard;
	protected Experiment expt;
	
	private final Map<DacTriggerId, TriggerChannel> triggers = Maps.newEnumMap(DacTriggerId.class);
	
	public FpgaModelBase(DacBoard dacBoard, Experiment expt) {
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
		int cycles = (int)Math.ceil(microseconds * FREQUENCY);
		addMemoryCommand(new DelayCommand(cycles));
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
	
	
	// SRAM calls
	
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
	
	public void setSramDualBlockDelay(double delay) {
		sramDualBlockDelay = delay;
		if (sramCalledDualBlock) {
			// need to update the already-created dual-block command
			sramDualBlockCmd.setDelay(delay);
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
		// add initial noop and final mem commands
		List<MemoryCommand> mem = Lists.newArrayList(memory);
		mem.add(0, NoopCommand.getInstance());
		mem.add(EndSequenceCommand.getInstance());
		
		// resolve addresses of all SRAM blocks
		for (MemoryCommand c : mem) {
			if (c instanceof CallSramCommand) {
				CallSramCommand cmd = (CallSramCommand)c;
				String block = cmd.getBlockName();
				cmd.setStartAddress(expt.getBlockStartAddress(block));
				cmd.setEndAddress(expt.getBlockEndAddress(block));
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
		return bits;
	}
	
	/**
	 * Get the bits for the full SRAM sequence for this board.
	 * We loop over all called blocks, padding the bits from each block
	 * and then concatenating them together.
	 * @return
	 */
	public long[] getSram() {
		// get bits for all SRAM blocks
		int len = 0;
		List<long[]> blocks = Lists.newArrayList();
		for (String blockName : expt.getBlockNames()) {
			long[] block = getSramBlock(blockName);
			padArrayFront(block, expt.getPaddedBlockLength(blockName));
			blocks.add(block);
			len += block.length;
		}
		// concatenate blocks into one array
		long[] sram = new long[len];
		int pos = 0;
		for (long[] block : blocks) {
			System.arraycopy(block, 0, sram, pos, block.length);
			pos += block.length;
		}
		return sram;
	}
		
	/**
	 * Get bits for the first block of a dual-block SRAM call
	 * @return
	 */
	public long[] getSramDualBlock1() {
		Preconditions.checkState(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call");
		return getSramBlock(sramDualBlockCmd.getBlockName1());
	}
	
	/**
	 * Get bits for the second block of a dual-block SRAM call
	 * @return
	 */
	public long[] getSramDualBlock2() {
		Preconditions.checkState(sramCalledDualBlock, "Sequence does not have a dual-block SRAM call");
		return getSramBlock(sramDualBlockCmd.getBlockName2(), false); // no autotrigger on second block
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
	 * Set trigger bits in an array of DAC bits.
	 * @param s
	 * @param block
	 */
	private void setTriggerBits(long[] s, String block, boolean addAutoTrigger) {
		for (TriggerChannel ch : triggers.values()) {
			boolean[] trigs = ch.getSramData(block);
			if (addAutoTrigger && (expt.getAutoTriggerId() == ch.getTriggerId())) {
				for (int i = 4; i < 4 + expt.getAutoTriggerLen(); i++) {
					if (i < trigs.length - 1) trigs[i] = true;
				}
			}
			long bit = 1L << ch.getShift();
			for (int i = 0; i < s.length; i++) {
				s[i] |= trigs[i] ? bit : 0;
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
}
