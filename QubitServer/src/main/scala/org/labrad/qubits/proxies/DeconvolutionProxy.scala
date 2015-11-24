package org.labrad.qubits.proxies

import org.labrad.Connection
import org.labrad.data._
import org.labrad.qubits.enums.DacAnalogId
import org.labrad.qubits.resources.DacBoard
import org.labrad.qubits.util.ComplexArray
import scala.collection.mutable
import scala.concurrent.{ExecutionContext, Future}

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
class DeconvolutionProxy(cxn: Connection)(implicit ec: ExecutionContext) {

  import DeconvolutionProxy._

  // TODO send requests in different contexts so that they can potentially be worked on in parallel

  private def startRequest() = {
    mutable.Buffer.empty[(String, Data)]
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
    req += "Board" -> Str(board.name)
    req += "DAC" -> Str(id.toString)
    req += "Set Settling" -> Cluster(Arr(settlingRates), Arr(settlingTimes))
    req += "Set Reflection" -> Cluster(Arr(reflectionRates), Arr(reflectionAmplitudes))
    val idx = req.size
    req += "Correct Analog" -> Cluster(Arr(data), Bool(averageEnds), Bool(dither))
    cxn.send(SERVER_NAME, req: _*).map { result =>
      result(idx).get[Array[Int]]
    }
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
    req += "Board" -> Str(board.name)
    req += "DAC" -> Str(id.toString)
    req += "Loop" -> Bool(false)
    req += "Set Settling" -> Cluster(Arr(settlingRates), Arr(settlingTimes))
    req += "Set Reflection" -> Cluster(Arr(reflectionRates), Arr(reflectionAmplitudes))
    req += "Time Offset" -> Value(t0, "ns")
    val idx = req.size
    req += "Correct Analog FT" -> Cluster(data.toData(), Bool(averageEnds), Bool(dither))
    cxn.send(SERVER_NAME, req: _*).map { result =>
      result(idx).get[Array[Int]]
    }
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
    req += "Board" -> Str(board.name)
    req += "Frequency" -> Value(freq, "GHz")
    val idx = req.length
    req += "Correct IQ" -> Cluster(data.toData(), Bool(averageEnds))
    cxn.send(SERVER_NAME, req: _*).map { result =>
      val (i, q) = result(idx).get[(Array[Int], Array[Int])]
      IqResult(i, q)
    }
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
    req += "Board" -> Str(board.name)
    req += "Frequency" -> Value(freq, "GHz")
    req += "Loop" -> Bool(false)
    req += "Time Offset" -> Value(t0, "ns")
    val idx = req.length
    req += "Correct IQ FT" -> Cluster(data.toData(), Bool(averageEnds))
    cxn.send(SERVER_NAME, req: _*).map { result =>
      val (i, q) = result(idx).get[(Array[Int], Array[Int])]
      IqResult(i, q)
    }
  }
}
