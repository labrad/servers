package org.labrad.qubits.channeldata

import java.util.concurrent.Future

import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.util.ComplexArray
import org.labrad.qubits.util.Futures

import com.google.common.base.Function

class AnalogDataFourier(data: ComplexArray, t0: Double, averageEnds: Boolean, dither: Boolean) extends AnalogDataBase {

  private var deconvolvedData: Array[Int] = null

  def checkLength(expected: Int): Unit = {
    val expectedFourier = if (expected % 2 == 0) (expected/2) + 1 else (expected+1) / 2
    LengthChecker.checkLengths(data.length, expectedFourier)
  }

  def deconvolve(deconvolver: DeconvolutionProxy): Future[Void] = {
    val ch = getChannel()
    val req = deconvolver.deconvolveAnalogFourier(
        ch.getDacBoard(),
        ch.getDacId(),
        data,
        t0,
        ch.getSettlingRates(),
        ch.getSettlingTimes(),
        ch.getReflectionRates(),
        ch.getReflectionAmplitudes(),
        averageEnds,
        dither
    )
    Futures.chain(req, new Function[Array[Int], Void] {
      override def apply(result: Array[Int]): Void = {
        deconvolvedData = result
        setDeconvolved(true)
        null
      }
    })
  }

  def getDeconvolved(): Array[Int] = {
    require(isDeconvolved(), "Data has not yet been deconvolved")
    deconvolvedData
  }
}
