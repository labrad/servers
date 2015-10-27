package org.labrad.qubits.channeldata

import org.labrad.qubits.channels.IqChannel
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.proxies.DeconvolutionProxy.IqResult
import org.labrad.qubits.util.ComplexArray
import scala.concurrent.{ExecutionContext, Future}

class IqDataFourier(data: ComplexArray, t0: Double, zeroEnds: Boolean) extends IqDataBase {

  @volatile private var I: Array[Int] = null
  @volatile private var Q: Array[Int] = null

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(data.length, expected)
  }

  def deconvolve(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit] = {
    val ch = getChannel()
    val freq = ch.getMicrowaveConfig().frequency
    val req = deconvolver.deconvolveIqFourier(ch.dacBoard, data, freq, t0, zeroEnds)
    req.map { result =>
      I = result.I
      Q = result.Q
      setDeconvolved(true)
    }
  }

  override def getDeconvolvedI(): Array[Int] = {
    require(isDeconvolved(), "Data has not yet been deconvolved")
    I
  }

  override def getDeconvolvedQ(): Array[Int] = {
    require(isDeconvolved(), "Data has not yet been deconvolved")
    Q
  }
}
