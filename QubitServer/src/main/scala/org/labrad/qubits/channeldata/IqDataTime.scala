package org.labrad.qubits.channeldata

import org.labrad.qubits.channels.IqChannel
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.proxies.DeconvolutionProxy.IqResult
import org.labrad.qubits.util.ComplexArray
import scala.concurrent.{ExecutionContext, Future}

class IqDataTime(data: ComplexArray, isDeconvolved: Boolean, zeroEnds: Boolean) extends IqDataBase {

  @volatile private var I: Array[Int] = null
  @volatile private var Q: Array[Int] = null

  if (isDeconvolved) {
    I = data.re.map { i => (i * 0x1fff).toInt & 0x3fff }
    Q = data.im.map { q => (q * 0x1fff).toInt & 0x3fff }
  }
  setDeconvolved(isDeconvolved)

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(data.length, expected)
  }

  override def deconvolve(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit] = {
    val ch = getChannel()
    val freq = ch.getMicrowaveConfig().frequency
    val req = deconvolver.deconvolveIq(ch.dacBoard, data, freq, zeroEnds)
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

class IqDataTimeDacified(I: Array[Int], Q: Array[Int]) extends IqDataBase {

  setDeconvolved(true)

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(I.length, expected)
    LengthChecker.checkLengths(Q.length, expected)
  }

  override def deconvolve(deconvolved: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit] = {
    sys.error("cannot deconvolve pre-dacified data")
  }

  override def getDeconvolvedI(): Array[Int] = I
  override def getDeconvolvedQ(): Array[Int] = Q
}
