package org.labrad.qubits;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Future;

import com.google.common.base.Preconditions;
import org.labrad.data.Request;
import org.labrad.qubits.channeldata.Deconvolvable;
import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.enums.DacAnalogId;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.resources.AnalogBoard;
import org.labrad.qubits.util.Futures;

import com.google.common.collect.Lists;
import com.google.common.collect.Maps;

public class FpgaModelAnalog extends FpgaModelDac {
  
  private AnalogBoard analogBoard;
  private Map<DacAnalogId, AnalogChannel> dacs = Maps.newEnumMap(DacAnalogId.class);
  
  public FpgaModelAnalog(AnalogBoard dacBoard, Experiment expt) {
    super(dacBoard, expt);
    analogBoard = dacBoard;
    // create dummy channels for this board
    /* pomalley 4/22/14 we no longer use dummy channels.
    for (DacAnalogId id : DacAnalogId.values()) {
      AnalogChannel dummy = new AnalogChannel("dummy_" + id.toString());
      dummy.setExperiment(expt);
      dummy.setDacBoard(dacBoard);
      dummy.setDacId(id);
      dummy.setFpgaModel(this);
    }*/
  }
  
  public AnalogBoard getAnalogBoard() {
    return analogBoard;
  }
  
  public void setAnalogChannel(DacAnalogId id, AnalogChannel ch) {
    dacs.put(id, ch);
  }
  
  public AnalogChannel getDacChannel(DacAnalogId id) {
    return dacs.get(id);
  }
  
  public Future<Void> deconvolveSram(DeconvolutionProxy deconvolver) {
    List<Future<Void>> deconvolutions = Lists.newArrayList();
    for (AnalogChannel ch : dacs.values()) {
      for (String blockName : getBlockNames()) {
        Deconvolvable block = ch.getBlockData(blockName);
        if (!block.isDeconvolved()) {
          deconvolutions.add(block.deconvolve(deconvolver));
        }
      }
    }
    return Futures.waitForAll(deconvolutions);
  }
  
  /**
   * Get sram bits for a particular block
   * @param block
   * @return
   */
  @Override
  protected long[] getSramDacBits(String block) {
    final long[] sram = new long[getBlockLength(block)];
    Arrays.fill(sram, 0);
    for (DacAnalogId id : dacs.keySet()) {
      int[] vals = dacs.get(id).getSramData(block);
      for (int i = 0; i < vals.length; i++) {
        sram[i] |= (long)((vals[i] & 0x3FFF) << id.getShift());
      }
    }
    return sram;
  }

	/**
	 * See comments on parent's abstract method.
	 */
    @Override
	protected boolean hasSramChannel() {
		return !dacs.isEmpty();
	}

  @Override
  public void addJumpTablePackets(Request runRequest) {
    if (!dacs.isEmpty()) {
      AnalogChannel ch = dacs.values().iterator().next();
      for (AnalogChannel other : dacs.values()) {
        Preconditions.checkArgument(ch.getJumpTable().equals(other.getJumpTable()),
                "Jump tables not equivalent for channels sharing a board: %s, %s", ch.getName(), ch.getName());
      }
      ch.getJumpTable().addPackets(runRequest);
    }
  }

  @Override
  public void clearJumpTable() {
    for (AnalogChannel ch : dacs.values()) {
      ch.clearJumpTable();
    }
  }
}
