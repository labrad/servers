package org.labrad.qubits.proxies

import java.util.List
import java.util.concurrent.Future

import org.labrad.Connection
import org.labrad.data.Data
import org.labrad.data.Request
import org.labrad.qubits.enums.DacAnalogId
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.util.ComplexArray
import org.labrad.qubits.util.Futures

import com.google.common.base.Function

object DeconvolutionProxy {
  val SERVER_NAME = "DAC Calibration"

  case class IqResult(I: Array[Int], Q: Array[Int])
}

/**
 * This class gives us a way to ask for data to be deconvolved before we pass it
 * to the DACs to be executed.  Currently, this works by sending requests to the
 * DAC Calibration server, which does the actual work.
 *
 */
class DeconvolutionProxy(cxn: Connection) {

  import DeconvolutionProxy._

  // TODO send requests in different contexts so that they can potentially be worked on in parallel

  private def startRequest(): Request = {
    new Request(SERVER_NAME)
  }

  /**
   * Deconvolve analog data specified in the time domain.
   * @param board
   * @param id
   * @param data
   * @param settlingRates
   * @param settlingTimes
   * @return
   */
  def deconvolveAnalog(board: DacBoard, id: DacAnalogId, data: Array[Double],
      settlingRates: Array[Double], settlingTimes: Array[Double],
      reflectionRates: Array[Double], reflectionAmplitudes: Array[Double],
      averageEnds: Boolean, dither: Boolean): Future[Array[Int]] = {
    val req = startRequest()
    req.add("Board", Data.valueOf(board.getName()))
    req.add("DAC", Data.valueOf(id.toString()))
    req.add("Set Settling", Data.valueOf(settlingRates), Data.valueOf(settlingTimes))
    req.add("Set Reflection", Data.valueOf(reflectionRates), Data.valueOf(reflectionAmplitudes))
    val idx = req.addRecord("Correct Analog",
        Data.valueOf(data), Data.valueOf(averageEnds), Data.valueOf(dither))
    Futures.chain(cxn.send(req), new Function[List[Data], Array[Int]] {
      override def apply(result: List[Data]): Array[Int] = {
        result.get(idx).getIntArray()
      }
    })
  }

  /**
   * Deconvolve analog data specified in the frequency domain.
   * @param board
   * @param id
   * @param data
   * @param t0
   * @param settlingRates
   * @param settlingTimes
   * @return
   */
  def deconvolveAnalogFourier(board: DacBoard, id: DacAnalogId, data: ComplexArray, t0: Double,
      settlingRates: Array[Double], settlingTimes: Array[Double],
      reflectionRates: Array[Double], reflectionAmplitudes: Array[Double],
      averageEnds: Boolean, dither: Boolean): Future[Array[Int]] = {
    val req = startRequest()
    req.add("Board", Data.valueOf(board.getName()))
    req.add("DAC", Data.valueOf(id.toString()))
    req.add("Loop", Data.valueOf(false))
    req.add("Set Settling", Data.valueOf(settlingRates), Data.valueOf(settlingTimes))
    req.add("Set Reflection", Data.valueOf(reflectionRates), Data.valueOf(reflectionAmplitudes))
    req.add("Time Offset", Data.valueOf(t0))
    val idx = req.addRecord("Correct Analog FT",
        data.toData(), Data.valueOf(averageEnds), Data.valueOf(dither))
    Futures.chain(cxn.send(req), new Function[List[Data], Array[Int]] {
      override def apply(result: List[Data]): Array[Int] = {
        result.get(idx).getIntArray()
      }
    })
  }

  /**
   * Deconvolve analog data specified in the time domain.
   * @param board
   * @param id
   * @param data
   * @param settlingRates
   * @param settlingTimes
   * @return
   */
  def deconvolveIq(board: DacBoard, data: ComplexArray, freq: Double, averageEnds: Boolean): Future[IqResult] = {
    val req = startRequest()
    req.add("Board", Data.valueOf(board.getName()))
    req.add("Frequency", Data.valueOf(freq))
    val idx = req.addRecord("Correct IQ", data.toData(), Data.valueOf(averageEnds))
    Futures.chain(cxn.send(req), new Function[List[Data], IqResult] {
      override def apply(result: List[Data]): IqResult = {
        val ans = result.get(idx)
        IqResult(ans.get(0).getIntArray(), ans.get(1).getIntArray())
      }
    })
  }

  /**
   * Deconvolve analog data specified in the frequency domain.
   * @param board
   * @param id
   * @param data
   * @param t0
   * @param settlingRates
   * @param settlingTimes
   * @return
   */
  def deconvolveIqFourier(board: DacBoard, data: ComplexArray, freq: Double, t0: Double, averageEnds: Boolean): Future[IqResult] = {
    val req = startRequest()
    req.add("Board", Data.valueOf(board.getName()))
    req.add("Frequency", Data.valueOf(freq))
    req.add("Loop", Data.valueOf(false))
    req.add("Time Offset", Data.valueOf(t0))
    val idx = req.addRecord("Correct IQ FT", data.toData(), Data.valueOf(averageEnds))
    Futures.chain(cxn.send(req), new Function[List[Data], IqResult] {
      override def apply(result: List[Data]): IqResult = {
        val ans = result.get(idx)
        IqResult(ans.get(0).getIntArray(), ans.get(1).getIntArray())
      }
    })
  }
}
