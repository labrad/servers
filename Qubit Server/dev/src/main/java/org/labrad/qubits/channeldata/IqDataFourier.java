package org.labrad.qubits.channeldata;

import java.util.concurrent.Future;

import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.proxies.DeconvolutionProxy.IqResult;
import org.labrad.qubits.util.ComplexArray;
import org.labrad.qubits.util.Futures;

import com.google.common.base.Function;
import com.google.common.base.Preconditions;

public class IqDataFourier extends IqDataBase {

  private ComplexArray data;
  private double t0;
  private int[] I, Q;

  public IqDataFourier(ComplexArray data, double t0) {
    this.data = data;
    this.t0 = t0;
  }

  public void checkLength(int expected) {
    LengthChecker.checkLengths(data.length, expected);
  }

  @Override
  public Future<Void> deconvolve(DeconvolutionProxy deconvolver) {
    IqChannel ch = getChannel();
    double freq = ch.getMicrowaveConfig().getFrequency();
    Future<DeconvolutionProxy.IqResult> req = deconvolver.deconvolveIqFourier(ch.getDacBoard(), data, freq, t0);
    return Futures.chain(req, new Function<DeconvolutionProxy.IqResult, Void>() {
      @Override
      public Void apply(IqResult result) {
        I = result.I;
        Q = result.Q;
        setDeconvolved(true);
        return null;
      }
    });
  }

  @Override
  public int[] getDeconvolvedI() {
    Preconditions.checkState(isDeconvolved(), "Data has not yet been deconvolved");
    return I;
  }

  @Override
  public int[] getDeconvolvedQ() {
    Preconditions.checkState(isDeconvolved(), "Data has not yet been deconvolved");
    return Q;
  }
}
