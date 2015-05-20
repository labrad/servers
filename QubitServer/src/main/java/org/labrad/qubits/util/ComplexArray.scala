package org.labrad.qubits.util;

import org.labrad.data.Complex;
import org.labrad.data.Data;

/**
 * A utility class that encapsulates an array of complex numbers.
 * 
 * This class is much more efficient than having an array of Complex objects
 * because only two arrays need to be allocated, not one object per element
 * in the array.  In addition, this class has convenience methods for converting
 * to and from LabRAD data.
 */
public class ComplexArray {
  public final double[] re;
  public final double[] im;
  public final int length;
  public ComplexArray(double[] re, double[] im) {
    this.re = re;
    this.im = im;
    this.length = re.length;
  }

  /**
   * Convert a complex array into LabRAD data of type *c
   */
  public Data toData() {
    Data iq = Data.ofType("*c");
    iq.setArraySize(re.length);
    for (int i = 0; i < re.length; i++) {
      iq.setComplex(re[i], im[i], i);
    }
    return iq;
  }

  /**
   * Create a complex array from LabRAD data of type *c
   * @param vals
   * @return
   */
  public static ComplexArray fromData(Data vals) {
    int len = vals.getArraySize();
    double[] re = new double[len];
    double[] im = new double[len];
    for (int i = 0; i < len; i++) {
      Complex c = vals.get(i).getComplex();
      re[i] = c.getReal();
      im[i] = c.getImag();
    }
    return new ComplexArray(re, im);
  }
}
