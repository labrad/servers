package org.labrad.qubits.channeldata

import org.labrad.qubits.proxies.DeconvolutionProxy
import scala.concurrent.{ExecutionContext, Future}

class AnalogDataTime(data: Array[Double], isDeconvolved: Boolean, averageEnds: Boolean, dither: Boolean) extends AnalogDataBase {

  @volatile private var deconvolvedData: Array[Int] = null

  if (isDeconvolved) {
    deconvolvedData = data.map { x =>
      (x * 0x1fff).toInt & 0x3fff
    }
  }
  setDeconvolved(isDeconvolved)

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(data.length, expected)
  }

  override def deconvolve(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit] = {
    val ch = getChannel()
    val req = deconvolver.deconvolveAnalog(
        ch.dacBoard,
        ch.getDacId(),
        data,
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

  override def getDeconvolved(): Array[Int] = {
    require(isDeconvolved(), "Data has not yet been deconvolved")
    deconvolvedData
  }
}

class AnalogDataTimeDacified(data: Array[Int]) extends AnalogDataBase {

  setDeconvolved(true)

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(data.length, expected)
  }

  override def deconvolve(deconvolver: DeconvolutionProxy)(implicit ec: ExecutionContext): Future[Unit] = {
    sys.error("cannot deconvolve pre-dacified data")
  }

  override def getDeconvolved(): Array[Int] = {
    data
  }
}
