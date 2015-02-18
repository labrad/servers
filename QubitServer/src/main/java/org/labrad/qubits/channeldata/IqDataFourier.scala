package org.labrad.qubits.channeldata

import java.util.concurrent.Future

import org.labrad.qubits.channels.IqChannel
import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.proxies.DeconvolutionProxy.IqResult
import org.labrad.qubits.util.ComplexArray
import org.labrad.qubits.util.Futures

import com.google.common.base.Function

class IqDataFourier(data: ComplexArray, t0: Double, zeroEnds: Boolean) extends IqDataBase {

  private var I: Array[Int] = null
  private var Q: Array[Int] = null

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(data.length, expected)
  }

  def deconvolve(deconvolver: DeconvolutionProxy): Future[Void] = {
    val ch = getChannel()
    val freq = ch.getMicrowaveConfig().getFrequency()
    val req = deconvolver.deconvolveIqFourier(ch.getDacBoard(), data, freq, t0, zeroEnds)
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
