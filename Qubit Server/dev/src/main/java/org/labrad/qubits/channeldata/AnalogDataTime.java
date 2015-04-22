package org.labrad.qubits.channeldata;

import java.util.concurrent.Future;

import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.proxies.DeconvolutionProxy;
import org.labrad.qubits.util.Futures;

import com.google.common.base.Function;
import com.google.common.base.Preconditions;

public class AnalogDataTime extends AnalogDataBase {

  private double[] rawData = null;
  private boolean averageEnds;
  private boolean dither;
  private int[] deconvolvedData = null;

  public AnalogDataTime(double[] data, boolean isDeconvolved, boolean averageEnds, boolean dither) {
    this.rawData = data;
    this.averageEnds = averageEnds;
    this.dither = dither;
    if (isDeconvolved) {
      int[] values = new int[data.length];
      for (int i = 0; i < data.length; i++) {
        values[i] = (int)(data[i] * 0x1fff) & 0x3fff;
      }
      this.deconvolvedData = values;
    }
    setDeconvolved(isDeconvolved);
  }

  public AnalogDataTime(int[] data) {
    this.deconvolvedData = data;
    this.averageEnds = false;
    setDeconvolved(true);
  }

  public void checkLength(int expected) {
    if (rawData == null) {
      LengthChecker.checkLengths(deconvolvedData.length, expected);
    } else {
      LengthChecker.checkLengths(rawData.length, expected);
    }
  }

  @Override
  public Future<Void> deconvolve(DeconvolutionProxy deconvolver) {
    AnalogChannel ch = getChannel();
    Future<int[]> req = deconvolver.deconvolveAnalog(
        ch.getDacBoard(),
        ch.getDacId(),
        rawData,
        ch.getSettlingRates(),
        ch.getSettlingTimes(),
        ch.getReflectionRates(),
        ch.getReflectionAmplitudes(),
        averageEnds,
        dither
    );
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
