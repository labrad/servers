package org.labrad.qubits.channeldata

import org.labrad.qubits.proxies.DeconvolutionProxy
import scala.concurrent.{ExecutionContext, Future}

trait Deconvolvable {
  /**
   * Whether the data for this block has been deconvolved.
   * @return
   */
  def isDeconvolved(): Boolean

  /**
   * Mark as needing to be deconvolved again.
   */
  def invalidate(): Unit

  /**
   * Deconvolve this item using the provided deconvolver.
   */
  def deconvolve(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit]
}
