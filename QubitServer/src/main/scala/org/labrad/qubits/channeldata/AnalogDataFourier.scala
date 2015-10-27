package org.labrad.qubits.channeldata

import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.util.ComplexArray
import scala.concurrent.{ExecutionContext, Future}

class AnalogDataFourier(data: ComplexArray, t0: Double, averageEnds: Boolean, dither: Boolean) extends AnalogDataBase {

  @volatile private var deconvolvedData: Array[Int] = null

  def checkLength(expected: Int): Unit = {
    val expectedFourier = if (expected % 2 == 0) (expected/2) + 1 else (expected+1) / 2
    LengthChecker.checkLengths(data.length, expectedFourier)
  }

  def deconvolve(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit] = {
    val ch = getChannel()
    val req = deconvolver.deconvolveAnalogFourier(
        ch.dacBoard,
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
    req.map { result =>
      deconvolvedData = result
      setDeconvolved(true)
    }
  }

  def getDeconvolved(): Array[Int] = {
    require(isDeconvolved(), "Data has not yet been deconvolved")
    deconvolvedData
  }
}
