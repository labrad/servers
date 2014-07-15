package org.labrad.qubits.channeldata;

import java.util.concurrent.Future;

import org.labrad.qubits.channels.IqChannel;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.proxies.DeconvolutionProxy.IqResult;
import org.labrad.qubits.util.ComplexArray;
import org.labrad.qubits.util.Futures;

import com.google.common.base.Function;
import com.google.common.base.Preconditions;

public class IqDataTime extends IqDataBase {

  private ComplexArray data;
  private int[] I, Q;

  public IqDataTime(ComplexArray data, boolean isDeconvolved) {
    this.data = data;
    if (isDeconvolved) {
      I = new int[data.re.length];
      Q = new int[data.im.length];
      for (int i = 0; i < data.length; i++) {
        I[i] = (int)(data.re[i] * 0x1fff) & 0x3fff;
        Q[i] = (int)(data.im[i] * 0x1fff) & 0x3fff;
      }
    }
    setDeconvolved(isDeconvolved);
  }

  public void checkLength(int expected) {
    LengthChecker.checkLengths(data.length, expected);
  }

  @Override
  public Future<Void> deconvolve(DeconvolutionProxy deconvolver) {
    IqChannel ch = getChannel();
    double freq = ch.getMicrowaveConfig().getFrequency();
    Future<DeconvolutionProxy.IqResult> req = deconvolver.deconvolveIq(ch.getDacBoard(), data, freq);
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
