package org.labrad.qubits;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.Future;

import org.labrad.data.Request;
import org.labrad.qubits.channeldata.Deconvolvable;
import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.resources.MicrowaveBoard;
import org.labrad.qubits.resources.MicrowaveSource;
import org.labrad.qubits.util.Futures;

import com.google.common.collect.Lists;

public class FpgaModelMicrowave extends FpgaModelDac {

  private MicrowaveBoard microwaveBoard;
  private IqChannel iq = null;

  public FpgaModelMicrowave(MicrowaveBoard dacBoard, Experiment expt) {
    super(dacBoard, expt);
    microwaveBoard = dacBoard;
    // create a dummy channel for this board
    /* pomalley 4/22/14 no longer use dummy channels
    IqChannel dummy = new IqChannel("dummy_iq");
    dummy.setExperiment(expt);
    dummy.setDacBoard(dacBoard);
    dummy.setMicrowaveSource(dacBoard.getMicrowaveSource());
    dummy.configMicrowavesOn(6.0, -10); // TODO reuse microwave config from another board that has same source
    dummy.setFpgaModel(this);
    */
  }

  public void setIqChannel(IqChannel iq) {
    this.iq = iq;
  }

  public IqChannel getIqChannel() {
    return iq;
  }

  public MicrowaveSource getMicrowaveSource() {
    return microwaveBoard.getMicrowaveSource();
  }

  public Future<Void> deconvolveSram(DeconvolutionProxy deconvolver) {
    List<Future<Void>> deconvolutions = Lists.newArrayList();
    for (String blockName : getBlockNames()) {
      Deconvolvable block = iq.getBlockData(blockName);
      if (!block.isDeconvolved()) {
        deconvolutions.add(block.deconvolve(deconvolver));
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
    if (iq != null) {
      int[] A = iq.getSramDataA(block);
      int[] B = iq.getSramDataB(block);
      for (int i = 0; i < A.length; i++) {
        sram[i] |= ((long)(A[i] & 0x3FFF)) + ((long)((B[i] & 0x3FFF) << 14));
      }
    }
    return sram;
  }

  	/**
  	 * See comment on parent's abstract method.
  	 */
	@Override
	protected boolean hasSramChannel() {
		return iq != null;
	}

  @Override
  public void addJumpTablePackets(Request runRequest) {
    if (iq != null) {
      iq.getJumpTable().addPackets(runRequest);
    }
  }

  @Override
  public void clearJumpTable() {
    if (iq != null) {
      iq.clearJumpTable();
    }
  }
}
