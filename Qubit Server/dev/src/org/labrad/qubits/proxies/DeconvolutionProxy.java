package org.labrad.qubits.proxies;

import java.util.List;
import java.util.concurrent.Future;

import org.labrad.Connection;
import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.qubits.enums.DacAnalogId;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.util.ComplexArray;
import org.labrad.qubits.util.Futures;

import com.google.common.base.Function;

/**
 * This class gives us a way to ask for data to be deconvolved before we pass it
 * to the DACs to be executed.  Currently, this works by sending requests to the
 * DAC Calibration server, which does the actual work.
 *
 */
public class DeconvolutionProxy {
  public static final String SERVER_NAME = "DAC Calibration";

  private Connection cxn;

  public DeconvolutionProxy(Connection cxn) {
    this.cxn = cxn;
  }

  // TODO send requests in different contexts so that they can potentially be worked on in parallel
  
  private Request startRequest() {
    return new Request(SERVER_NAME);
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
  public Future<int[]> deconvolveAnalog(DacBoard board, DacAnalogId id, double[] data,
      double[] settlingRates, double[] settlingTimes) {
    Request req = startRequest();
    req.add("Board", Data.valueOf(board.getName()));
    req.add("DAC", Data.valueOf(id.toString()));
    req.add("Set Settling", Data.valueOf(settlingRates), Data.valueOf(settlingTimes));
    final int idx = req.addRecord("Correct", Data.valueOf(data));
    return Futures.chain(cxn.send(req), new Function<List<Data>, int[]>() {
      @Override
      public int[] apply(List<Data> result) {
        return result.get(idx).getIntArray();
      }
    });
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
  public Future<int[]> deconvolveAnalogFourier(DacBoard board, DacAnalogId id, ComplexArray data, double t0,
      double[] settlingRates, double[] settlingTimes) {
    Request req = startRequest();
    req.add("Board", Data.valueOf(board.getName()));
    req.add("DAC", Data.valueOf(id.toString()));
    req.add("Loop", Data.valueOf(false));
    req.add("Set Settling", Data.valueOf(settlingRates), Data.valueOf(settlingTimes));
    req.add("Time Offset", Data.valueOf(t0));
    final int idx = req.addRecord("Correct FT", data.toData());
    return Futures.chain(cxn.send(req), new Function<List<Data>, int[]>() {
      @Override
      public int[] apply(List<Data> result) {
        return result.get(idx).getIntArray();
      }
    });
  }

  public static class IqResult {
    public final int[] I;
    public final int[] Q;
    IqResult(int[] I, int[] Q) {
      this.I = I;
      this.Q = Q;
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
  public Future<IqResult> deconvolveIq(DacBoard board, ComplexArray data, double freq) {
    Request req = startRequest();
    req.add("Board", Data.valueOf(board.getName()));
    req.add("Frequency", Data.valueOf(freq));
    final int idx = req.addRecord("Correct", data.toData());
    return Futures.chain(cxn.send(req), new Function<List<Data>, IqResult>() {
      @Override
      public IqResult apply(List<Data> result) {
        Data ans = result.get(idx);
        return new IqResult(ans.get(0).getIntArray(), ans.get(1).getIntArray());
      }
    });
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
  public Future<IqResult> deconvolveIqFourier(DacBoard board, ComplexArray data, double freq, double t0) {
    Request req = startRequest();
    req.add("Board", Data.valueOf(board.getName()));
    req.add("Frequency", Data.valueOf(freq));
    req.add("Loop", Data.valueOf(false));
    req.add("Time Offset", Data.valueOf(t0));
    final int idx = req.addRecord("Correct FT", data.toData());
    return Futures.chain(cxn.send(req), new Function<List<Data>, IqResult>() {
      @Override
      public IqResult apply(List<Data> result) {
        Data ans = result.get(idx);
        return new IqResult(ans.get(0).getIntArray(), ans.get(1).getIntArray());
      }
    });
  }
}
