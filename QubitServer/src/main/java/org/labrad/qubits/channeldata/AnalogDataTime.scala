package org.labrad.qubits.channeldata

import java.util.concurrent.Future

import org.labrad.qubits.proxies.DeconvolutionProxy
import org.labrad.qubits.util.Futures

import com.google.common.base.Function

class AnalogDataTime(data: Array[Double], isDeconvolved: Boolean, averageEnds: Boolean, dither: Boolean) extends AnalogDataBase {

  private var deconvolvedData: Array[Int] = null

  if (isDeconvolved) {
    deconvolvedData = data.map { x =>
      (x * 0x1fff).toInt & 0x3fff
    }
  }
  setDeconvolved(isDeconvolved)

  def checkLength(expected: Int): Unit = {
    LengthChecker.checkLengths(data.length, expected)
  }

  override def deconvolve(deconvolver: DeconvolutionProxy): Future[Void] = {
    val ch = getChannel()
    val req = deconvolver.deconvolveAnalog(
        ch.getDacBoard(),
        ch.getDacId(),
        data,
        ch.getSettlingRates(),
        ch.getSettlingTimes(),
        ch.getReflectionRates(),
        ch.getReflectionAmplitudes(),
        averageEnds,
        dither)
    Futures.chain(req, new Function[Array[Int], Void] {
      override def apply(result: Array[Int]): Void = {
        deconvolvedData = result
        setDeconvolved(true)
        null
      }
    })
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

  override def deconvolve(deconvolver: DeconvolutionProxy): Future[Void] = {
    sys.error("cannot deconvolve pre-dacified data")
  }

  override def getDeconvolved(): Array[Int] = {
    data
  }
}
