package org.labrad.qubits.channeldata;

import java.util.concurrent.Future;

import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.util.ComplexArray;
import org.labrad.qubits.util.Futures;

import com.google.common.base.Function;
import com.google.common.base.Preconditions;

public class AnalogDataFourier extends AnalogDataBase {

  private ComplexArray data;
  private double t0;
  private int[] deconvolvedData;

  public AnalogDataFourier(ComplexArray data, double t0) {
    this.data = data;
    this.t0 = t0;
  }

  public void checkLength(int expected) {
    int expectedFourier = expected % 2 == 0 ? (expected/2) + 1 : (expected+1) / 2;
    LengthChecker.checkLengths(data.length, expectedFourier);
  }

  @Override
  public Future<Void> deconvolve(DeconvolutionProxy deconvolver) {
    AnalogChannel ch = getChannel();
    Future<int[]> req = deconvolver.deconvolveAnalogFourier(ch.getDacBoard(), ch.getDacId(), data, t0, ch.getSettlingRates(), ch.getSettlingTimes());
    return Futures.chain(req, new Function<int[], Void>() {
      @Override
      public Void apply(int[] result) {
        deconvolvedData = result;
        setDeconvolved(true);
        return null;
      }
    });
  }

  @Override
  public int[] getDeconvolved() {
    Preconditions.checkState(isDeconvolved(), "Data has not yet been deconvolved");
    return deconvolvedData;
  }
}
