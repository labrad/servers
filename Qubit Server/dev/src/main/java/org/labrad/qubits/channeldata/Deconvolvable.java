package org.labrad.qubits.channeldata;

import java.util.concurrent.Future;

import org.labrad.qubits.proxies.DeconvolutionProxy;

public interface Deconvolvable {
  /**
   * Whether the data for this block has been deconvolved.
   * @return
   */
  public boolean isDeconvolved();

  /**
   * Mark as needing to be deconvolved again.
   */
  public void invalidate();
  
  /**
   * Deconvolve this item using the provided deconvolver.
   */
  public Future<Void> deconvolve(DeconvolutionProxy deconvolver);
}
