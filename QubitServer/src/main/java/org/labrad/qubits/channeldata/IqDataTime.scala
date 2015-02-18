package org.labrad.qubits.channeldata

import java.util.concurrent.Future

import org.labrad.qubits.channels.IqChannel
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.proxies.DeconvolutionProxy.IqResult
import org.labrad.qubits.util.ComplexArray
import org.labrad.qubits.util.Futures

import com.google.common.base.Function

class IqDataTime(data: ComplexArray, isDeconvolved: Boolean, zeroEnds: Boolean) extends IqDataBase {

  private var I: Array[Int] = null
  private var Q: Array[Int] = null

  if (isDeconvolved) {
    I = data.re.map { i => (i * 0x1fff).toInt & 0x3fff }
    Q = data.im.map { q => (q * 0x1fff).toInt & 0x3fff }
  }
  setDeconvolved(isDeconvolved)

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(data.length, expected)
  }

  override def deconvolve(deconvolver: DeconvolutionProxy): Future[Void] = {
    val ch = getChannel()
    val freq = ch.getMicrowaveConfig().getFrequency()
    val req = deconvolver.deconvolveIq(ch.getDacBoard(), data, freq, zeroEnds)
    Futures.chain(req, new Function[DeconvolutionProxy.IqResult, Void] {
      override def apply(result: IqResult): Void = {
        I = result.I
        Q = result.Q
        setDeconvolved(true)
        null
      }
    })
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

  override def deconvolve(deconvolved: DeconvolutionProxy): Future[Void] = {
    sys.error("cannot deconvolve pre-dacified data")
  }

  override def getDeconvolvedI(): Array[Int] = I
  override def getDeconvolvedQ(): Array[Int] = Q
}
